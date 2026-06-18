from __future__ import annotations

import argparse
import logging
import subprocess
import sys

import load_classicmodels
import run_glue_job
import validate_pipeline

from common import BASE_DIR, configure_logging


TERRAFORM_DIR = BASE_DIR / "terraform"


def run_terraform(dry_run: bool, auto_approve: bool) -> int:
    logging.info("Passo 1/5 - Inicializando Terraform")
    subprocess.run(["terraform", f"-chdir={TERRAFORM_DIR}", "init"], check=True)

    if dry_run:
        logging.info("Passo 2/5 - Executando dry-run com terraform plan")
        subprocess.run(["terraform", f"-chdir={TERRAFORM_DIR}", "plan"], check=True)
        logging.info("Dry-run concluido. Encerrando sem aplicar mudancas.")
        return 0

    logging.info("Passo 2/5 - Aplicando infraestrutura com Terraform")
    apply_command = ["terraform", f"-chdir={TERRAFORM_DIR}", "apply"]
    if auto_approve:
        apply_command.append("-auto-approve")
    subprocess.run(apply_command, check=True)
    return 0


def run_step(step_name: str, step_number: str, fn) -> int:
    logging.info("%s - %s", step_number, step_name)
    return fn()


def main() -> int:
    parser = argparse.ArgumentParser(description="Orquestrador do pipeline ETL da task 2")
    parser.add_argument("--dry-run", action="store_true", help="Executa apenas terraform init + terraform plan")
    parser.add_argument("--auto-approve", action="store_true", help="Executa terraform apply com -auto-approve")
    args = parser.parse_args()

    configure_logging()
    logging.info("=== INICIANDO PIPELINE ETL ===")

    try:
        terraform_status = run_terraform(dry_run=args.dry_run, auto_approve=args.auto_approve)
        if terraform_status != 0 or args.dry_run:
            return terraform_status

        load_status = run_step("Carregando e validando o banco de origem", "Passo 3/4", load_classicmodels.main)
        if load_status != 0:
            return load_status

        glue_status = run_step("Executando o Glue Job", "Passo 4/4", run_glue_job.main)
        if glue_status != 0:
            return glue_status

        validation_status = run_step("Validando as saidas do ETL", "Passo 5/5", validate_pipeline.main)
        if validation_status != 0:
            return validation_status
    except subprocess.CalledProcessError as exc:
        logging.error("Falha ao executar Terraform. Codigo de saida: %s", exc.returncode)
        return 1

    logging.info("=== PIPELINE ETL CONCLUIDO COM SUCESSO ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
