"""
Validação do Pipeline ETL - classicmodels lab

Verifica:
  1. Status do último Glue Job Run (ou aguarda conclusão)
  2. Presença dos arquivos Parquet no S3 para todas as entidades
  3. Consistência dos dados (contagem mínima, integridade referencial)
  4. Regra de negócio: sales_amount == quantity_ordered * price_each

Exit codes:
  0 -> todas as validações passaram
  1 -> uma ou mais validações falharam
"""

import argparse
import io
import json
import logging
import os
import sys
import time

import boto3
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# --- Configurações ---------------------------------------------------------------
CONFIG = {
    "region":             "us-east-1",
    "credentials_file":   os.path.join("..", "rds_credentials.json"),
    "glue_job_name":      "classicmodels-etl-job",   # atualizado pelo setup_tfvars
    "expected_entities":  [
        "fact_orders",
        "dim_customers",
        "dim_products",
        "dim_dates",
        "dim_countries",
    ],
    "min_rows": {
        "fact_orders":   100,   # classicmodels tem ~2.996 order lines
        "dim_customers":   5,
        "dim_products":    5,
        "dim_dates":       5,
        "dim_countries":   1,
    },
    "poll_interval_s":  30,
    "max_wait_minutes": 60,
}

# --- Logging ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# --- Acumulador de resultados ----------------------------------------------------
RESULTS: list[dict] = []   # {"check": str, "passed": bool, "detail": str}


def record(check: str, passed: bool, detail: str = "") -> bool:
    icon = "OK" if passed else "X"
    fn = logger.info if passed else logger.error
    fn(f"  [{icon}] {check}" + (f" - {detail}" if detail else ""))
    RESULTS.append({"check": check, "passed": passed, "detail": detail})
    return passed


def load_json_file(path: str) -> dict:
    """Carrega JSON aceitando as codificações mais comuns de saída do Terraform/PowerShell."""
    last_error = None
    for encoding in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            with open(path, encoding=encoding) as f:
                return json.load(f)
        except (UnicodeError, json.JSONDecodeError) as e:
            last_error = e

    raise json.JSONDecodeError(
        f"Arquivo JSON inválido ou com codificação incompatível: {path} ({last_error})",
        "",
        0,
    )


# --- AWS clients (lazy) ----------------------------------------------------------
_session = None


def aws(service: str):
    global _session
    if _session is None:
        _session = boto3.Session(region_name=CONFIG["region"])
    return _session.client(service)


# ================================================================
# Passo 1 - Carrega configuração do bucket/job do terraform output
# ================================================================

def load_infra_config(dry_run: bool) -> tuple[str, str]:
    """
    Lê bucket e job_name do terraform output (ou dos valores padrão do CONFIG).
    Em dry_run, apenas exibe sem validar na AWS.
    """
    glue_job  = CONFIG["glue_job_name"]
    s3_bucket = None

    # Tenta ler do arquivo de output do terraform (se existir)
    tf_output_file = os.path.join("tf_outputs.json")
    if os.path.exists(tf_output_file):
        tf_out = load_json_file(tf_output_file)
        glue_job  = tf_out.get("glue_job_name", {}).get("value", glue_job)
        s3_bucket = tf_out.get("s3_bucket_name", {}).get("value")
        logger.info(f"  Configuração carregada de '{tf_output_file}'")
    elif os.path.exists("rds_credentials.json"):
        creds = load_json_file("rds_credentials.json")
        account_id = aws("sts").get_caller_identity()["Account"]
        s3_bucket  = f"{creds['database']}-etl-{account_id}"
        logger.info(f"  Bucket inferido: {s3_bucket}")
    else:
        logger.warning(
            "  tf_outputs.json não encontrado. Gere com:\n"
            "    terraform output -json > tf_outputs.json"
        )
        sys.exit(1)

    logger.info(f"  Glue Job : {glue_job}")
    logger.info(f"  S3 Bucket: {s3_bucket}")
    return glue_job, s3_bucket


# ================================================================
# Passo 2 - Dispara (opcional) e aguarda o Glue Job
# ================================================================

def trigger_glue_job(job_name: str, dry_run: bool) -> str | None:
    """Dispara o Glue Job e retorna o run_id."""
    if dry_run:
        logger.info(f"  [DRY-RUN] Dispararia job '{job_name}' (sem efeito real).")
        return None
    logger.info(f"  Disparando job '{job_name}'...")
    resp   = aws("glue").start_job_run(JobName=job_name)
    run_id = resp["JobRunId"]
    logger.info(f"  Job Run ID: {run_id}")
    return run_id


def get_last_run(job_name: str) -> dict | None:
    """Retorna o run mais recente do job (qualquer status)."""
    try:
        resp = aws("glue").get_job_runs(JobName=job_name, MaxResults=1)
        runs = resp.get("JobRuns", [])
        return runs[0] if runs else None
    except ClientError as e:
        logger.error(f"  Erro ao buscar runs do job '{job_name}': {e}")
        return None


def wait_for_job(job_name: str, run_id: str | None, dry_run: bool) -> bool:
    """
    Aguarda o job terminar (SUCCEEDED ou FAILED/STOPPED).
    Se run_id=None, monitora o run mais recente.
    Retorna True se SUCCEEDED.
    """
    if dry_run:
        logger.info("  [DRY-RUN] Pulando monitoramento do job.")
        return True

    glue        = aws("glue")
    max_polls   = (CONFIG["max_wait_minutes"] * 60) // CONFIG["poll_interval_s"]
    terminal    = {"SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"}
    last_status = None

    for attempt in range(1, max_polls + 1):
        try:
            if run_id:
                resp   = glue.get_job_run(JobName=job_name, RunId=run_id)
                run    = resp["JobRun"]
            else:
                run = get_last_run(job_name)
                if not run:
                    logger.error("  Nenhum run encontrado para o job.")
                    return False
                run_id = run["Id"]

            status = run["JobRunState"]

            if status != last_status:
                elapsed = run.get("ExecutionTime", 0)
                logger.info(f"  [{attempt}/{max_polls}] Status: {status} - {elapsed}s decorridos")
                last_status = status

            if status in terminal:
                if status == "SUCCEEDED":
                    logger.info(f"  OK Job concluído com SUCCEEDED em {run.get('ExecutionTime',0)}s")
                    return True
                else:
                    msg = run.get("ErrorMessage", "sem mensagem de erro")
                    logger.error(f"  FAIL Job terminou com status '{status}': {msg}")
                    return False

        except ClientError as e:
            logger.warning(f"  Erro ao consultar status (tentativa {attempt}): {e}")

        time.sleep(CONFIG["poll_interval_s"])

    logger.error(f"  FAIL Timeout após {CONFIG['max_wait_minutes']} minutos sem conclusão.")
    return False


# ================================================================
# Passo 3 - Verifica arquivos Parquet no S3
# ================================================================

def list_parquet_files(s3_client, bucket: str, prefix: str) -> list[dict]:
    """Lista objetos Parquet em um prefixo S3."""
    paginator = s3_client.get_paginator("list_objects_v2")
    files     = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet") or obj["Key"].endswith(".snappy.parquet"):
                files.append(obj)
    return files


def check_s3_outputs(bucket: str, dry_run: bool) -> bool:
    """Valida que todos os arquivos Parquet esperados existem no S3."""
    if dry_run:
        logger.info("  [DRY-RUN] Checagem S3 pulada.")
        return True

    s3      = aws("s3")
    all_ok  = True

    for entity in CONFIG["expected_entities"]:
        prefix = f"data/{entity}/"
        files  = list_parquet_files(s3, bucket, prefix)
        has    = len(files) > 0
        size   = sum(f["Size"] for f in files)
        detail = f"{len(files)} arquivo(s), {size / 1024:.1f} KB" if has else "nenhum arquivo encontrado"
        if not record(f"S3 parquet existe: {entity}", has, detail):
            all_ok = False

    return all_ok


# ================================================================
# Passo 4 - Lê e valida os dados
# ================================================================

def read_parquet_from_s3(bucket: str, entity: str) -> "pyarrow.Table":
    """Baixa todos os arquivos Parquet de uma entidade e retorna como Table."""
    s3    = aws("s3")
    files = list_parquet_files(s3, bucket, f"data/{entity}/")
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo Parquet em s3://{bucket}/data/{entity}/")

    tables = []
    for obj in files:
        response = s3.get_object(Bucket=bucket, Key=obj["Key"])
        buf      = io.BytesIO(response["Body"].read())
        tables.append(pq.read_table(buf))

    import pyarrow as pa
    return pa.concat_tables(tables)


def check_row_counts(bucket: str, dry_run: bool) -> bool:
    """Valida contagem mínima de linhas em cada entidade."""
    if dry_run:
        logger.info("  [DRY-RUN] Checagem de contagens pulada.")
        return True

    all_ok = True
    for entity, min_rows in CONFIG["min_rows"].items():
        try:
            table  = read_parquet_from_s3(bucket, entity)
            count  = table.num_rows
            passed = count >= min_rows
            detail = f"{count:,} linhas (mínimo: {min_rows:,})"
            if not record(f"Contagem mínima: {entity}", passed, detail):
                all_ok = False
        except Exception as e:
            record(f"Contagem mínima: {entity}", False, f"Erro ao ler: {e}")
            all_ok = False

    return all_ok


def check_referential_integrity(bucket: str, dry_run: bool) -> bool:
    """
    Verifica integridade referencial: todas as chaves da fact_orders
    devem existir nas dimensões correspondentes.
    """
    if dry_run:
        logger.info("  [DRY-RUN] Checagem de integridade referencial pulada.")
        return True

    all_ok = True
    try:
        fact   = read_parquet_from_s3(bucket, "fact_orders").to_pandas()
        cust   = read_parquet_from_s3(bucket, "dim_customers").to_pandas()
        prod   = read_parquet_from_s3(bucket, "dim_products").to_pandas()
        dates  = read_parquet_from_s3(bucket, "dim_dates").to_pandas()
        ctry   = read_parquet_from_s3(bucket, "dim_countries").to_pandas()

        checks = [
            ("customer_id -> dim_customers",
             set(fact["customer_id"]).issubset(set(cust["customer_id"]))),
            ("product_id -> dim_products",
             set(fact["product_id"]).issubset(set(prod["product_id"]))),
            ("order_date_key -> dim_dates",
             set(fact["order_date_key"]).issubset(set(dates["date_key"]))),
            ("country_key -> dim_countries",
             set(fact["country_key"].dropna()).issubset(set(ctry["country_key"]))),
        ]

        for label, passed in checks:
            if not record(f"Integridade referencial: {label}", passed):
                all_ok = False

    except Exception as e:
        record("Integridade referencial", False, f"Erro: {e}")
        all_ok = False

    return all_ok


def check_sales_amount(bucket: str, dry_run: bool) -> bool:
    """
    Valida regra de negócio: sales_amount == quantity_ordered * price_each
    (tolerância de 1 centavo para arredondamentos de ponto flutuante).
    """
    if dry_run:
        logger.info("  [DRY-RUN] Checagem de sales_amount pulada.")
        return True

    try:
        fact         = read_parquet_from_s3(bucket, "fact_orders").to_pandas()
        expected     = fact["quantity_ordered"] * fact["price_each"]
        diff         = (fact["sales_amount"] - expected).abs()
        inconsistent = int((diff > 0.01).sum())
        total        = len(fact)

        passed = inconsistent == 0
        detail = (
            f"0 inconsistências em {total:,} registros"
            if passed
            else f"{inconsistent:,} registros com sales_amount inconsistente"
        )
        return record("sales_amount == quantity_ordered * price_each", passed, detail)

    except Exception as e:
        return record("sales_amount == quantity_ordered * price_each", False, f"Erro: {e}")


# ================================================================
# Entry Point
# ================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Valida o pipeline ETL do classicmodels lab"
    )
    parser.add_argument(
        "--trigger",
        action="store_true",
        help="Dispara o Glue Job antes de monitorar (default: usa o run mais recente)",
    )
    parser.add_argument(
        "--skip-wait",
        action="store_true",
        help="Pula o aguardo do job e vai direto para a validação de dados",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula as operações sem fazer chamadas destrutivas",
    )
    return parser.parse_args()


def print_summary() -> int:
    """Imprime resumo e retorna exit code."""
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = sum(1 for r in RESULTS if not r["passed"])
    total  = len(RESULTS)

    print()
    print("=" * 60)
    print("  RESUMO DA VALIDAÇÃO")
    print("=" * 60)
    print(f"  Total de verificações : {total}")
    print(f"  Aprovadas             : {passed}")
    print(f"  Reprovadas            : {failed}")
    print("-" * 60)

    if failed > 0:
        print("  FALHAS:")
        for r in RESULTS:
            if not r["passed"]:
                print(f"    FAIL {r['check']}")
                if r["detail"]:
                    print(f"      {r['detail']}")

    print("=" * 60)
    status = "APROVADO" if failed == 0 else "REPROVADO"
    print(f"  RESULTADO FINAL: {status}")
    print("=" * 60)

    return 0 if failed == 0 else 1


def main():
    cli_args = parse_args()
    dry_run  = cli_args.dry_run

    print("=" * 60)
    print("  Validação ETL - classicmodels lab")
    if dry_run:
        print("  *** MODO DRY-RUN (sem efeito real) ***")
    print("=" * 60)

    # -- Configuração ----------------------------------------------
    logger.info("\n[SETUP] Carregando configuração...")
    job_name, bucket = load_infra_config(dry_run)

    # -- Disparo (opcional) ----------------------------------------
    run_id = None
    if cli_args.trigger:
        logger.info("\n[1/4] Disparando Glue Job...")
        run_id = trigger_glue_job(job_name, dry_run)
    else:
        logger.info("\n[1/4] Usando run mais recente (--trigger não informado)...")

    # -- Aguarda conclusão -----------------------------------------
    if not cli_args.skip_wait:
        logger.info("\n[2/4] Aguardando conclusão do Glue Job...")
        job_ok = wait_for_job(job_name, run_id, dry_run)
        record("Glue Job finalizado com SUCCEEDED", job_ok)
        if not job_ok and not dry_run:
            logger.error("  Job não concluiu com SUCCEEDED. Verifique os logs no Glue console.")
            # Continua validação mesmo com falha para diagnosticar o problema
    else:
        logger.info("\n[2/4] Monitoramento de job pulado (--skip-wait).")

    # -- Verifica S3 -----------------------------------------------
    logger.info("\n[3/4] Verificando arquivos Parquet no S3...")
    s3_ok = check_s3_outputs(bucket, dry_run)

    # -- Valida dados ----------------------------------------------
    logger.info("\n[4/4] Validando qualidade dos dados...")
    if s3_ok and not dry_run:
        try:
            import pandas  # noqa: F401
        except ImportError:
            logger.error(
                "  pandas não instalado. Execute:\n"
                "    pip install pandas pyarrow"
            )
            sys.exit(1)

        check_row_counts(bucket, dry_run)
        check_referential_integrity(bucket, dry_run)
        check_sales_amount(bucket, dry_run)
    elif not s3_ok:
        logger.warning("  Pulando validação de dados - arquivos S3 ausentes.")

    # -- Resumo ----------------------------------------------------
    exit_code = print_summary()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
