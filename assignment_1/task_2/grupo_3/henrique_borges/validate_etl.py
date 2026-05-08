"""
Valida o resultado do ETL:
  1. Último run do Glue job: SUCCEEDED
  2. Arquivos Parquet existem no S3 para todas as tabelas
  3. fact_orders tem registros e chaves válidas nas dimensões
  4. sales_amount == quantity_ordered * price_each
"""
import io
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

import boto3

info_path = BASE_DIR / "pipeline_info.json"
if not info_path.exists():
    print("[ERRO] pipeline_info.json não encontrado. Execute 'terraform apply' primeiro.")
    sys.exit(1)

info          = json.loads(info_path.read_text())
S3_BUCKET     = info["s3_bucket_name"]
GLUE_JOB_NAME = info["glue_job_name"]
S3_PREFIX     = "data/"
EXPECTED      = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]

session = boto3.Session(
    aws_access_key_id     = os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"],
    aws_session_token     = os.environ.get("AWS_SESSION_TOKEN"),
    region_name           = os.environ.get("AWS_REGION", "us-east-1"),
)
glue = session.client("glue")
s3   = session.client("s3")

PASS   = "[PASS]"
FAIL   = "[FAIL]"
errors = []


def check(condition, msg):
    print(f"  {PASS if condition else FAIL} {msg}")
    if not condition:
        errors.append(msg)


def list_parquet_keys(prefix):
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                keys.append(obj["Key"])
    return keys


def read_table(table_name):
    import pyarrow as pa
    import pyarrow.parquet as pq

    keys = list_parquet_keys(f"{S3_PREFIX}{table_name}/")
    if not keys:
        return None
    parts = []
    for key in keys:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        parts.append(pq.read_table(io.BytesIO(obj["Body"].read())))
    return pa.concat_tables(parts).to_pandas()


# --- 1. Glue job status ---
print("\n=== 1. Status do Glue Job ===")
runs = glue.get_job_runs(JobName=GLUE_JOB_NAME, MaxResults=1).get("JobRuns", [])
if not runs:
    check(False, f"Nenhum run encontrado para '{GLUE_JOB_NAME}'")
else:
    state = runs[0]["JobRunState"]
    check(state == "SUCCEEDED", f"Último run: {state}")

# --- 2. Arquivos Parquet no S3 ---
print("\n=== 2. Parquet no S3 ===")
for table in EXPECTED:
    keys = list_parquet_keys(f"{S3_PREFIX}{table}/")
    check(len(keys) > 0, f"s3://{S3_BUCKET}/{S3_PREFIX}{table}/ tem {len(keys)} arquivo(s)")

# --- 3 & 4. Conteúdo da fact_orders ---
print("\n=== 3 & 4. Conteúdo e FKs da fact_orders ===")
try:
    import pyarrow  # noqa — dispara ImportError cedo se não instalado

    fact = read_table("fact_orders")
    check(fact is not None and len(fact) > 0, f"fact_orders tem {len(fact) if fact is not None else 0} linhas")

    if fact is not None and len(fact) > 0:
        required = {
            "order_id", "customer_id", "product_id",
            "order_date_key", "country_key",
            "quantity_ordered", "price_each", "sales_amount",
        }
        check(required.issubset(set(fact.columns)), "Todas as colunas obrigatórias presentes")

        if required.issubset(set(fact.columns)):
            # FK: country_key ∈ dim_countries
            dim_c = read_table("dim_countries")
            if dim_c is not None:
                orphans = set(fact["country_key"]) - set(dim_c["country_key"])
                check(len(orphans) == 0, f"country_key válido em dim_countries ({len(orphans)} órfão(s))")

            # FK: order_date_key ∈ dim_dates
            dim_d = read_table("dim_dates")
            if dim_d is not None:
                orphans = set(fact["order_date_key"]) - set(dim_d["date_key"])
                check(len(orphans) == 0, f"order_date_key válido em dim_dates ({len(orphans)} órfão(s))")

            # Consistência: sales_amount == quantity_ordered * price_each
            expected_amount = (fact["quantity_ordered"] * fact["price_each"]).round(2)
            mismatches = (expected_amount != fact["sales_amount"].round(2)).sum()
            check(mismatches == 0, f"sales_amount == quantity_ordered * price_each ({mismatches} divergências)")

except ImportError:
    print("  [WARN] pyarrow não instalado — pulando validação de conteúdo")
    print("         Execute: pip install pyarrow pandas")

# --- Resumo ---
print("\n" + "=" * 50)
if errors:
    print(f"REPROVADO — {len(errors)} verificação(ões) falharam:")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print("APROVADO — todas as verificações passaram.")
    sys.exit(0)
