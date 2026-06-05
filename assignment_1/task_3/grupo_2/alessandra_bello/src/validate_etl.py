"""
Valida o resultado do ETL no S3.

Critérios (Task 2.6):
  1. Job Glue finalizou com SUCCEEDED
  2. Parquet de fact_orders e todas as dimensões existem no S3
  3. Schema: colunas obrigatórias do contrato Task 2 presentes
  4. fact_orders tem registros (mínimo realista) e referencia chaves válidas
  5. sales_amount == quantity_ordered * price_each (tolerância float)

Exit code: 0 = tudo ok, 1 = alguma falha.
"""

import logging
import os
import sys
from io import BytesIO

import boto3
import pandas as pd

import envlocal

envlocal.load()

JOB_NAME = os.environ.get("GLUE_JOB_NAME", "classicmodels-etl-job")
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = "data"
REGION = os.environ.get("AWS_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "projetos")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("validate_etl")

EXPECTED_TABLES = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]

# Contagens realistas baseadas no sample classicmodels.
# fact_orders ~= orderdetails (2996). Dimensões a partir das tabelas origem.
MIN_ROWS = {
    "fact_orders": 2900,    # ~2996 orderdetails
    "dim_customers": 100,   # 122 customers
    "dim_products": 100,    # 110 products
    "dim_dates": 200,       # ~252 dias únicos no sample
    "dim_countries": 20,    # ~27 países distintos
}

# Schema obrigatório por tabela (Task 2 contrato).
REQUIRED_COLUMNS = {
    "fact_orders": [
        "order_id", "customer_id", "product_id",
        "order_date_key", "country_key",
        "quantity_ordered", "price_each", "sales_amount",
    ],
    "dim_customers": ["customer_id", "customer_name", "contact_name", "city", "country"],
    "dim_products": ["product_id", "product_name", "product_line", "product_vendor"],
    "dim_dates": ["date_key", "full_date", "year", "quarter", "month", "day"],
    "dim_countries": ["country_key", "country", "territory"],
}

failures: list[str] = []


def ok(msg: str) -> None:
    log.info("  [ok]   %s", msg)


def fail(msg: str) -> None:
    log.error("  [FAIL] %s", msg)
    failures.append(msg)


def list_parquet(s3, table: str) -> list[str]:
    prefix = f"{S3_PREFIX}/{table}/"
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]


def read_parquet(s3, keys: list[str]) -> pd.DataFrame:
    if not keys:
        return pd.DataFrame()
    frames = []
    for key in keys:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        frames.append(pd.read_parquet(BytesIO(obj["Body"].read())))
    return pd.concat(frames, ignore_index=True)


def check_job_status(glue) -> None:
    log.info("=== 1. Glue job status ===")
    runs = glue.get_job_runs(JobName=JOB_NAME, MaxResults=1)["JobRuns"]
    if not runs:
        fail("Nenhum run encontrado para o job")
        return
    last = runs[0]
    state = last["JobRunState"]
    run_id = last["Id"]
    if state == "SUCCEEDED":
        ok(f"Job {run_id} -> {state}")
    else:
        fail(f"Job {run_id} -> {state} (esperado SUCCEEDED)")


def check_parquet_files(s3) -> dict[str, list[str]]:
    log.info("=== 2. Parquet no S3 ===")
    parquet_keys = {}
    for table in EXPECTED_TABLES:
        keys = list_parquet(s3, table)
        if keys:
            ok(f"{table}: {len(keys)} arquivo(s) Parquet")
            parquet_keys[table] = keys
        else:
            fail(f"{table}: nenhum Parquet em s3://{S3_BUCKET}/{S3_PREFIX}/{table}/")
    return parquet_keys


def check_schema(dfs: dict[str, pd.DataFrame]) -> None:
    log.info("=== 3. Schema (colunas obrigatórias) ===")
    for table, required in REQUIRED_COLUMNS.items():
        df = dfs.get(table)
        if df is None or df.empty:
            fail(f"{table}: DataFrame vazio, schema não verificado")
            continue
        missing = [c for c in required if c not in df.columns]
        if not missing:
            ok(f"{table}: todas as {len(required)} colunas obrigatórias presentes")
        else:
            fail(f"{table}: faltam colunas {missing}")


def check_row_counts(dfs: dict[str, pd.DataFrame]) -> None:
    log.info("=== 4a. Contagens mínimas ===")
    for table, minimum in MIN_ROWS.items():
        df = dfs.get(table)
        n = 0 if df is None else len(df)
        if n >= minimum:
            ok(f"{table}: {n} registros (mínimo {minimum})")
        else:
            fail(f"{table}: {n} registros (mínimo {minimum})")


def check_foreign_keys(dfs: dict[str, pd.DataFrame]) -> None:
    log.info("=== 4b. Integridade referencial ===")
    fact = dfs.get("fact_orders")
    if fact is None or fact.empty:
        fail("fact_orders vazio, FK checks pulados")
        return

    fk_map = [
        ("customer_id", "dim_customers", "customer_id"),
        ("product_id", "dim_products", "product_id"),
        ("order_date_key", "dim_dates", "date_key"),
        ("country_key", "dim_countries", "country_key"),
    ]
    for fact_col, dim_table, dim_col in fk_map:
        dim = dfs.get(dim_table)
        if dim is None or dim.empty:
            fail(f"{dim_table} vazio, FK {fact_col} não verificado")
            continue
        valid = set(dim[dim_col])
        orphans = fact[~fact[fact_col].isin(valid)]
        if orphans.empty:
            ok(f"fact_orders.{fact_col} -> {dim_table}.{dim_col}: sem órfãos")
        else:
            fail(f"fact_orders.{fact_col}: {len(orphans)} órfão(s)")


def check_sales_amount(dfs: dict[str, pd.DataFrame]) -> None:
    log.info("=== 5. Regra sales_amount == quantity_ordered * price_each ===")
    fact = dfs.get("fact_orders")
    if fact is None or fact.empty:
        fail("fact_orders vazio, regra não verificada")
        return
    expected = (fact["quantity_ordered"] * fact["price_each"]).round(2)
    actual = fact["sales_amount"].round(2)
    mismatch = (expected - actual).abs() > 0.01
    n_bad = mismatch.sum()
    if n_bad == 0:
        ok(f"sales_amount consistente em {len(fact)} registros")
    else:
        fail(f"sales_amount inconsistente em {n_bad} registro(s)")


def main() -> int:
    if os.environ.get("DRY_RUN") == "1":
        log.info("DRY_RUN=1 → plano:")
        log.info("  1) verificar último run de %s", JOB_NAME)
        log.info("  2) listar Parquet em s3://%s/%s/ para %d tabelas",
                 S3_BUCKET, S3_PREFIX, len(EXPECTED_TABLES))
        log.info("  3) validar schema (%d tabelas)", len(REQUIRED_COLUMNS))
        log.info("  4) validar contagens (min) + FK (4 dimensões)")
        log.info("  5) validar sales_amount = quantity_ordered * price_each")
        return 0

    log.info("Profile=%s Region=%s Bucket=%s", PROFILE, REGION, S3_BUCKET)
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    glue = session.client("glue")
    s3 = session.client("s3")

    check_job_status(glue)
    parquet_keys = check_parquet_files(s3)

    dfs = {t: read_parquet(s3, keys) for t, keys in parquet_keys.items()}

    if set(EXPECTED_TABLES) <= set(dfs.keys()):
        check_schema(dfs)
        check_row_counts(dfs)
        check_foreign_keys(dfs)
        check_sales_amount(dfs)
    else:
        log.warning("  [skip] schema/contagem/FK/regra — Parquet faltando")

    log.info("=" * 50)
    if failures:
        log.error("RESULTADO: FALHOU — %d verificação(ões) com erro:", len(failures))
        for f in failures:
            log.error("  - %s", f)
        return 1
    log.info("RESULTADO: PASSOU — todas as verificações ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
