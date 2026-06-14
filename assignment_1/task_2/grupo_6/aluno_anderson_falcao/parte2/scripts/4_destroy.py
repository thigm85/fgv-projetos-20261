#!/usr/bin/env python3
"""
4_destroy.py - Destroi os recursos do laboratorio classicmodels.

O script pode ser executado a partir de qualquer diretorio. Ele remove:
  1. Execucoes em andamento do Glue Job
  2. Recursos Terraform da Task 2 (S3, Glue, endpoints, SG do Glue, regra RDS)
  3. Regra residual Glue -> RDS, se ainda existir
  4. RDS instance, DB subnet group e Security Group criados na Task 1
  5. Arquivos locais sensiveis/gerados, para permitir rodar tudo novamente

Flags:
  --dry-run   Exibe o que seria destruido sem executar nada.
  --yes       Pula confirmacoes interativas.
"""

import argparse
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, WaiterError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------
REGION = "us-east-1"
PROJECT_NAME = "classicmodels"

SCRIPT_DIR = Path(__file__).resolve().parent
PARTE2_DIR = SCRIPT_DIR.parent
STUDENT_DIR = PARTE2_DIR.parent
TF_FOLDER = PARTE2_DIR / "terraform"

CREDS_FILE = STUDENT_DIR / "rds_credentials.json"
TFVARS_FILE = TF_FOLDER / "terraform.tfvars"
TF_DIR = TF_FOLDER / ".terraform"
TF_LOCK_FILE = TF_FOLDER / ".terraform.lock.hcl"
TF_STATE_FILES = [
    TF_FOLDER / "terraform.tfstate",
    TF_FOLDER / "terraform.tfstate.backup",
]
TF_OUTPUT_FILES = [
    PARTE2_DIR / "tf_outputs.json",
    TF_FOLDER / "tf_outputs.json",
]

GLUE_JOB_NAME = f"{PROJECT_NAME}-etl-job"
RDS_INSTANCE_ID = f"{PROJECT_NAME}-db"
RDS_SG_NAME = f"{PROJECT_NAME}-db-sg"
GLUE_SG_NAME = f"{PROJECT_NAME}-glue-sg"
RDS_SUBNET_GROUP_NAME = f"{RDS_INSTANCE_ID}-subnet-group"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run(
    cmd: list[str],
    check: bool = True,
    capture: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    log.info("$ %s%s", " ".join(cmd), f"  (cwd={cwd})" if cwd else "")
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def confirm(msg: str, auto_yes: bool) -> bool:
    if auto_yes:
        log.info("%s -> confirmado via --yes", msg)
        return True
    resp = input(f"\n{msg} [s/N]: ").strip().lower()
    return resp in ("s", "sim", "y", "yes")


def is_client_error(error: ClientError, code: str) -> bool:
    return error.response.get("Error", {}).get("Code") == code or code in str(error)


def ec2_default_vpc_id(ec2) -> str | None:
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}]).get("Vpcs", [])
    return vpcs[0]["VpcId"] if vpcs else None


def describe_sg_by_name(ec2, group_name: str) -> dict | None:
    filters = [{"Name": "group-name", "Values": [group_name]}]
    vpc_id = ec2_default_vpc_id(ec2)
    if vpc_id:
        filters.append({"Name": "vpc-id", "Values": [vpc_id]})

    groups = ec2.describe_security_groups(Filters=filters).get("SecurityGroups", [])
    return groups[0] if groups else None


# ---------------------------------------------------------------------------
# Passo 1 - Glue Job
# ---------------------------------------------------------------------------
def stop_glue_job(dry_run: bool):
    log.info("-- Passo 1: Glue Job --")
    glue = boto3.client("glue", region_name=REGION)

    try:
        runs = glue.get_job_runs(JobName=GLUE_JOB_NAME, MaxResults=25).get("JobRuns", [])
        running = [
            r for r in runs
            if r.get("JobRunState") in ("RUNNING", "STARTING", "STOPPING")
        ]

        if not running:
            log.info("Nenhuma execucao em andamento do Glue Job '%s'.", GLUE_JOB_NAME)
            return

        for run_info in running:
            run_id = run_info["Id"]
            if dry_run:
                log.info("[DRY-RUN] Pararia job run %s", run_id)
            else:
                glue.batch_stop_job_run(JobName=GLUE_JOB_NAME, JobRunIds=[run_id])
                log.info("Job run %s interrompido.", run_id)
    except ClientError as e:
        if is_client_error(e, "EntityNotFoundException"):
            log.info("Glue Job '%s' nao encontrado.", GLUE_JOB_NAME)
        else:
            log.warning("Erro ao verificar job runs: %s", e)


# ---------------------------------------------------------------------------
# Passo 2 - terraform destroy
# ---------------------------------------------------------------------------
def terraform_destroy(dry_run: bool, auto_yes: bool):
    log.info("-- Passo 2: terraform destroy --")

    if not (TF_FOLDER / "main.tf").exists():
        log.warning("main.tf nao encontrado em '%s'. Pulando terraform destroy.", TF_FOLDER)
        return

    if dry_run:
        log.info("[DRY-RUN] Executaria: terraform destroy -auto-approve em '%s'", TF_FOLDER)
        return

    if not confirm("Destruir recursos Terraform da Task 2 (S3, Glue, endpoints, SGs)?", auto_yes):
        log.info("Terraform destroy cancelado pelo usuario.")
        return

    try:
        run(["terraform", "destroy", "-auto-approve"], cwd=TF_FOLDER)
        log.info("Terraform destroy concluido.")
    except subprocess.CalledProcessError:
        log.error("terraform destroy falhou. Verifique o output acima e tente novamente.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Passo 3 - regra residual Glue -> RDS
# ---------------------------------------------------------------------------
def remove_rds_glue_ingress_rule(dry_run: bool):
    """
    Remove somente a regra de ingress 3306 cujo source e o SG do Glue.
    Isso evita apagar outras regras legitimas do SG do RDS.
    """
    log.info("-- Passo 3: Regra ingress Glue -> RDS no SG do RDS --")
    ec2 = boto3.client("ec2", region_name=REGION)

    try:
        rds_sg = describe_sg_by_name(ec2, RDS_SG_NAME)
        if not rds_sg:
            log.info("SG do RDS '%s' nao encontrado.", RDS_SG_NAME)
            return

        glue_sg = describe_sg_by_name(ec2, GLUE_SG_NAME)
        glue_sg_id = glue_sg["GroupId"] if glue_sg else None

        rules = []
        for perm in rds_sg.get("IpPermissions", []):
            if perm.get("IpProtocol") != "tcp" or perm.get("FromPort") != 3306 or perm.get("ToPort") != 3306:
                continue

            matching_pairs = [
                pair for pair in perm.get("UserIdGroupPairs", [])
                if pair.get("GroupId") == glue_sg_id
                or pair.get("GroupName") == GLUE_SG_NAME
                or pair.get("Description") == "Permite MySQL do Glue ETL Job"
            ]
            if matching_pairs:
                rules.append(
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 3306,
                        "ToPort": 3306,
                        "UserIdGroupPairs": matching_pairs,
                    }
                )

        if not rules:
            log.info("Nenhuma regra Glue -> RDS encontrada.")
            return

        if dry_run:
            log.info("[DRY-RUN] Removeria %d regra(s) do SG %s", len(rules), rds_sg["GroupId"])
            return

        ec2.revoke_security_group_ingress(GroupId=rds_sg["GroupId"], IpPermissions=rules)
        log.info("Regra(s) Glue -> RDS removida(s) do SG do RDS.")
    except ClientError as e:
        log.warning("Erro ao remover regra do SG do RDS: %s", e)


# ---------------------------------------------------------------------------
# Passo 4 - RDS instance
# ---------------------------------------------------------------------------
def destroy_rds(dry_run: bool, auto_yes: bool):
    log.info("-- Passo 4: RDS Instance --")
    rds = boto3.client("rds", region_name=REGION)

    try:
        db = rds.describe_db_instances(DBInstanceIdentifier=RDS_INSTANCE_ID)["DBInstances"][0]
    except ClientError as e:
        if is_client_error(e, "DBInstanceNotFound"):
            log.info("RDS '%s' nao encontrado.", RDS_INSTANCE_ID)
            return
        raise

    status = db.get("DBInstanceStatus")
    if status == "deleting":
        log.info("RDS '%s' ja esta em delecao.", RDS_INSTANCE_ID)
    elif dry_run:
        log.info("[DRY-RUN] Deletaria RDS instance '%s'", RDS_INSTANCE_ID)
        return
    else:
        if not confirm(f"Deletar RDS instance '{RDS_INSTANCE_ID}' sem snapshot final?", auto_yes):
            log.info("Delecao do RDS cancelada.")
            return

        rds.delete_db_instance(
            DBInstanceIdentifier=RDS_INSTANCE_ID,
            SkipFinalSnapshot=True,
            DeleteAutomatedBackups=True,
        )
        log.info("Delecao do RDS iniciada.")

    log.info("Aguardando delecao do RDS (pode levar alguns minutos)...")
    waiter = rds.get_waiter("db_instance_deleted")
    try:
        waiter.wait(
            DBInstanceIdentifier=RDS_INSTANCE_ID,
            WaiterConfig={"Delay": 20, "MaxAttempts": 45},
        )
        log.info("RDS deletado com sucesso.")
    except (WaiterError, ClientError) as e:
        log.warning("Nao foi possivel confirmar a delecao do RDS: %s", e)


# ---------------------------------------------------------------------------
# Passo 5 - DB Subnet Group e Security Group do RDS
# ---------------------------------------------------------------------------
def destroy_rds_subnet_group(dry_run: bool):
    log.info("-- Passo 5a: DB Subnet Group do RDS --")
    rds = boto3.client("rds", region_name=REGION)

    try:
        rds.describe_db_subnet_groups(DBSubnetGroupName=RDS_SUBNET_GROUP_NAME)
    except ClientError as e:
        if is_client_error(e, "DBSubnetGroupNotFoundFault"):
            log.info("DB subnet group '%s' nao encontrado.", RDS_SUBNET_GROUP_NAME)
            return
        raise

    if dry_run:
        log.info("[DRY-RUN] Deletaria DB subnet group '%s'", RDS_SUBNET_GROUP_NAME)
        return

    try:
        rds.delete_db_subnet_group(DBSubnetGroupName=RDS_SUBNET_GROUP_NAME)
        log.info("DB subnet group '%s' deletado.", RDS_SUBNET_GROUP_NAME)
    except ClientError as e:
        log.warning("Erro ao deletar DB subnet group '%s': %s", RDS_SUBNET_GROUP_NAME, e)


def destroy_rds_sg(dry_run: bool):
    log.info("-- Passo 5b: Security Group do RDS --")
    ec2 = boto3.client("ec2", region_name=REGION)

    try:
        sg = describe_sg_by_name(ec2, RDS_SG_NAME)
        if not sg:
            log.info("SG '%s' nao encontrado.", RDS_SG_NAME)
            return

        if dry_run:
            log.info("[DRY-RUN] Deletaria SG '%s' (%s)", RDS_SG_NAME, sg["GroupId"])
            return

        for attempt in range(1, 7):
            try:
                ec2.delete_security_group(GroupId=sg["GroupId"])
                log.info("SG do RDS '%s' deletado.", RDS_SG_NAME)
                return
            except ClientError as e:
                if is_client_error(e, "InvalidGroup.NotFound"):
                    log.info("SG ja deletado.")
                    return
                if is_client_error(e, "DependencyViolation") and attempt < 6:
                    log.info("SG ainda em uso; nova tentativa em 10s (%d/6).", attempt)
                    time.sleep(10)
                    continue
                raise
    except ClientError as e:
        if is_client_error(e, "DependencyViolation"):
            log.warning("SG '%s' ainda em uso por outro recurso. Verifique no console.", RDS_SG_NAME)
        else:
            log.warning("Erro ao deletar SG do RDS: %s", e)


# ---------------------------------------------------------------------------
# Passo 6 - Arquivos locais
# ---------------------------------------------------------------------------
def cleanup_local_files(dry_run: bool):
    log.info("-- Passo 6: Arquivos locais --")
    targets = [
        CREDS_FILE,
        TFVARS_FILE,
        TF_LOCK_FILE,
        TF_DIR,
        *TF_STATE_FILES,
        *TF_OUTPUT_FILES,
    ]

    for target in targets:
        if not target.exists():
            log.info("Nao encontrado (ja removido): %s", target)
            continue

        if dry_run:
            kind = "diretorio" if target.is_dir() else "arquivo"
            log.info("[DRY-RUN] Removeria %s '%s'", kind, target)
            continue

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        log.info("Removido: %s", target)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Destroi todos os recursos do projeto classicmodels.")
    parser.add_argument("--dry-run", action="store_true", help="Simula a destruicao sem executar nada.")
    parser.add_argument("--yes", action="store_true", help="Pula confirmacoes interativas.")
    args = parser.parse_args()

    if args.dry_run:
        log.info("=" * 60)
        log.info("  MODO DRY-RUN - nenhuma alteracao sera feita")
        log.info("=" * 60)

    log.info("Iniciando destruicao do projeto '%s'...", PROJECT_NAME)
    log.info("Diretorio Terraform: %s", TF_FOLDER)

    stop_glue_job(args.dry_run)
    terraform_destroy(args.dry_run, args.yes)
    remove_rds_glue_ingress_rule(args.dry_run)
    destroy_rds(args.dry_run, args.yes)
    destroy_rds_subnet_group(args.dry_run)
    destroy_rds_sg(args.dry_run)
    cleanup_local_files(args.dry_run)

    log.info("=" * 60)
    if args.dry_run:
        log.info("  DRY-RUN concluido. Rode sem --dry-run para destruir.")
    else:
        log.info("  Destruicao concluida.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
