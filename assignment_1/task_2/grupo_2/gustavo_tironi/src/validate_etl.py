"""
Valida o resultado do ETL no S3.
Critérios (rubric 3):
  1. Job Glue finalizou com SUCCEEDED
  2. Parquet de fact_orders e todas as dimensões existem no S3
  3. fact_orders tem registros e referencia chaves válidas das dimensões
  4. sales_amount == quantity_ordered * price_each (tolerância float)
Exit code: 0 = tudo ok, 1 = alguma falha.
"""

import os
import sys
import math
import envlocal
import boto3
import pandas as pd
from io import BytesIO

envlocal.load()

JOB_NAME  = os.environ.get("GLUE_JOB_NAME", "classicmodels-etl-job")
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = "data"
REGION    = "us-east-1"
PROFILE   = "projetos"

session   = boto3.Session(profile_name=PROFILE, region_name=REGION)
glue      = session.client("glue")
s3        = session.client("s3")

EXPECTED_TABLES = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]
MIN_ROWS        = {"fact_orders": 1, "dim_customers": 1, "dim_products": 1, "dim_dates": 1, "dim_countries": 1}

failures = []

def ok(msg):
    print(f"  [ok]  {msg}")

def fail(msg):
    print(f"  [FAIL] {msg}")
    failures.append(msg)


# ── 1. Job status ─────────────────────────────────────────────────────────────
print("\n=== 1. Glue job status ===")
runs = glue.get_job_runs(JobName=JOB_NAME, MaxResults=1)["JobRuns"]
if not runs:
    fail("Nenhum run encontrado para o job")
else:
    last = runs[0]
    state = last["JobRunState"]
    run_id = last["Id"]
    if state == "SUCCEEDED":
        ok(f"Job {run_id} -> {state}")
    else:
        fail(f"Job {run_id} -> {state} (esperado SUCCEEDED)")


# ── 2. Parquet existem no S3 ──────────────────────────────────────────────────
print("\n=== 2. Parquet no S3 ===")

def list_parquet(table):
    prefix = f"{S3_PREFIX}/{table}/"
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]

parquet_keys = {}
for table in EXPECTED_TABLES:
    keys = list_parquet(table)
    if keys:
        ok(f"{table}: {len(keys)} arquivo(s) Parquet")
        parquet_keys[table] = keys
    else:
        fail(f"{table}: nenhum Parquet encontrado em s3://{S3_BUCKET}/{S3_PREFIX}/{table}/")


# ── helpers ───────────────────────────────────────────────────────────────────
def read_parquet(table):
    keys = parquet_keys.get(table, [])
    if not keys:
        return pd.DataFrame()
    frames = []
    for key in keys:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        frames.append(pd.read_parquet(BytesIO(obj["Body"].read())))
    return pd.concat(frames, ignore_index=True)


# ── 3. Integridade referencial ────────────────────────────────────────────────
print("\n=== 3. Integridade referencial ===")

if set(EXPECTED_TABLES) <= set(parquet_keys.keys()):
    fact        = read_parquet("fact_orders")
    dim_cust    = read_parquet("dim_customers")
    dim_prod    = read_parquet("dim_products")
    dim_dates   = read_parquet("dim_dates")
    dim_country = read_parquet("dim_countries")

    # contagem mínima
    for table, df in [("fact_orders", fact), ("dim_customers", dim_cust),
                      ("dim_products", dim_prod), ("dim_dates", dim_dates),
                      ("dim_countries", dim_country)]:
        n = len(df)
        if n >= MIN_ROWS[table]:
            ok(f"{table}: {n} registros")
        else:
            fail(f"{table}: {n} registros (mínimo {MIN_ROWS[table]})")

    # FK: customer_id
    valid_cust = set(dim_cust["customer_id"])
    orphan_cust = fact[~fact["customer_id"].isin(valid_cust)]
    if orphan_cust.empty:
        ok("fact_orders.customer_id -> dim_customers: sem órfãos")
    else:
        fail(f"fact_orders.customer_id: {len(orphan_cust)} órfão(s)")

    # FK: product_id
    valid_prod = set(dim_prod["product_id"])
    orphan_prod = fact[~fact["product_id"].isin(valid_prod)]
    if orphan_prod.empty:
        ok("fact_orders.product_id -> dim_products: sem órfãos")
    else:
        fail(f"fact_orders.product_id: {len(orphan_prod)} órfão(s)")

    # FK: order_date_key
    valid_dates = set(dim_dates["date_key"])
    orphan_dates = fact[~fact["order_date_key"].isin(valid_dates)]
    if orphan_dates.empty:
        ok("fact_orders.order_date_key -> dim_dates: sem órfãos")
    else:
        fail(f"fact_orders.order_date_key: {len(orphan_dates)} órfão(s)")

    # FK: country_key
    valid_country = set(dim_country["country_key"])
    orphan_country = fact[~fact["country_key"].isin(valid_country)]
    if orphan_country.empty:
        ok("fact_orders.country_key -> dim_countries: sem órfãos")
    else:
        fail(f"fact_orders.country_key: {len(orphan_country)} órfão(s)")

    # ── 4. Regra de negócio: sales_amount ────────────────────────────────────
    print("\n=== 4. Regra sales_amount == quantity_ordered * price_each ===")
    expected = (fact["quantity_ordered"] * fact["price_each"]).round(2)
    actual   = fact["sales_amount"].round(2)
    mismatch = (expected - actual).abs() > 0.01
    n_bad = mismatch.sum()
    if n_bad == 0:
        ok(f"sales_amount consistente em {len(fact)} registros")
    else:
        fail(f"sales_amount inconsistente em {n_bad} registro(s)")
else:
    print("  [skip] integridade e regras puladas — arquivos Parquet faltando")


# ── resultado ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
if failures:
    print(f"RESULTADO: FALHOU — {len(failures)} verificação(ões) com erro:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULTADO: PASSOU — todas as verificações ok")
    sys.exit(0)
