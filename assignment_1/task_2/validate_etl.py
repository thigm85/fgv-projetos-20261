"""
Validação do Pipeline ETL — Task 2

Este script verifica os 4 critérios de aceitação do enunciado:
  1. O Glue Job finalizou com status SUCCEEDED
  2. As saídas Parquet de fact_orders e das dimensões existem no S3
  3. A tabela fato contém registros e referencia chaves válidas das dimensões
  4. sales_amount == quantity_ordered * price_each em todos os registros

Uso:
  python validate_etl.py

  O script detecta automaticamente o bucket e job name consultando os
  recursos AWS criados pelo Terraform. Opcionalmente aceita argumentos:

  python validate_etl.py --job-name NOME --bucket BUCKET --region REGIAO

Requer: boto3, pyarrow, pandas
  pip install boto3 pyarrow pandas
"""

import argparse
import sys
from io import BytesIO

import boto3
import pandas as pd
import pyarrow.parquet as pq


# ─── Configuração ───────────────────────────────────────────────────────────
PROJECT_NAME = "classicmodels-etl"

EXPECTED_TABLES = [
    "fact_orders",
    "dim_customers",
    "dim_products",
    "dim_dates",
    "dim_countries",
]

FACT_DIMENSION_KEYS = {
    "customer_id": "dim_customers",
    "product_id": "dim_products",
    "order_date_key": "dim_dates",
    "country_key": "dim_countries",
}

DIM_PK = {
    "dim_customers": "customer_id",
    "dim_products": "product_id",
    "dim_dates": "date_key",
    "dim_countries": "country_key",
}


# ─── Auto-detect ────────────────────────────────────────────────────────────
def detect_bucket(region: str) -> str:
    """Detecta o bucket de output do ETL via AWS account ID."""
    sts = boto3.client("sts", region_name=region)
    account_id = sts.get_caller_identity()["Account"]
    return f"{PROJECT_NAME}-output-{account_id}"


def detect_job_name() -> str:
    """Retorna o nome padrão do Glue Job."""
    return f"{PROJECT_NAME}-job"


# ─── Helpers ────────────────────────────────────────────────────────────────
class ValidationResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, msg: str):
        self.passed += 1
        print(f"  ✅ {msg}")

    def fail(self, msg: str):
        self.failed += 1
        self.errors.append(msg)
        print(f"  ❌ {msg}")

    @property
    def success(self) -> bool:
        return self.failed == 0


def read_parquet_from_s3(s3_client, bucket: str, prefix: str) -> pd.DataFrame:
    """Lê todos os arquivos Parquet de um prefix no S3 e retorna um DataFrame."""
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if "Contents" not in response:
        return pd.DataFrame()

    parquet_files = [
        obj["Key"]
        for obj in response["Contents"]
        if obj["Key"].endswith(".parquet")
    ]

    if not parquet_files:
        return pd.DataFrame()

    dfs = []
    for key in parquet_files:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        table = pq.read_table(BytesIO(obj["Body"].read()))
        dfs.append(table.to_pandas())

    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


# ─── Validações ─────────────────────────────────────────────────────────────
def validate_job_status(glue_client, job_name: str, result: ValidationResult):
    """Critério 1: O job finalizou com status SUCCEEDED."""
    print("\n📋 Critério 1: Status do Glue Job")

    try:
        response = glue_client.get_job_runs(JobName=job_name, MaxResults=1)
        runs = response.get("JobRuns", [])

        if not runs:
            result.fail(f"Nenhuma execução encontrada para o job '{job_name}'")
            return

        latest_run = runs[0]
        status = latest_run["JobRunState"]
        run_id = latest_run["Id"]

        if status == "SUCCEEDED":
            result.ok(f"Job '{job_name}' (run {run_id}) finalizou com SUCCEEDED")
        else:
            result.fail(
                f"Job '{job_name}' (run {run_id}) status: {status} "
                f"(esperado: SUCCEEDED)"
            )

    except Exception as e:
        result.fail(f"Erro ao consultar job: {e}")


def validate_parquet_exists(s3_client, bucket: str, result: ValidationResult):
    """Critério 2: Saídas Parquet existem no S3 para todas as tabelas."""
    print("\n📋 Critério 2: Existência dos Parquets no S3")

    for table in EXPECTED_TABLES:
        prefix = f"{table}/"
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
        has_objects = response.get("KeyCount", 0) > 0

        if has_objects:
            result.ok(f"s3://{bucket}/{prefix} contém objetos")
        else:
            result.fail(f"s3://{bucket}/{prefix} está vazio ou não existe")


def validate_referential_integrity(
    s3_client, bucket: str, result: ValidationResult
) -> dict[str, pd.DataFrame]:
    """Critério 3: Fact contém registros e referencia chaves válidas."""
    print("\n📋 Critério 3: Integridade referencial")

    tables = {}
    for table in EXPECTED_TABLES:
        df = read_parquet_from_s3(s3_client, bucket, f"{table}/")
        tables[table] = df

    fact = tables.get("fact_orders", pd.DataFrame())

    if fact.empty:
        result.fail("fact_orders está vazia")
        return tables

    result.ok(f"fact_orders contém {len(fact)} registros")

    for fk_col, dim_table in FACT_DIMENSION_KEYS.items():
        dim_df = tables.get(dim_table, pd.DataFrame())
        if dim_df.empty:
            result.fail(
                f"{dim_table} está vazia — não é possível validar FK '{fk_col}'"
            )
            continue

        pk_col = DIM_PK[dim_table]
        fact_keys = set(fact[fk_col].dropna().unique())
        dim_keys = set(dim_df[pk_col].dropna().unique())
        orphans = fact_keys - dim_keys

        if not orphans:
            result.ok(
                f"Todas as chaves '{fk_col}' de fact_orders existem em "
                f"{dim_table}.{pk_col}"
            )
        else:
            result.fail(
                f"{len(orphans)} chave(s) órfã(s) em fact_orders.{fk_col} "
                f"sem correspondência em {dim_table}.{pk_col}: "
                f"{list(orphans)[:5]}..."
            )

    return tables


def validate_sales_amount(
    tables: dict[str, pd.DataFrame], result: ValidationResult
):
    """Critério 4: sales_amount == quantity_ordered * price_each."""
    print("\n📋 Critério 4: Consistência de sales_amount")

    fact = tables.get("fact_orders", pd.DataFrame())
    if fact.empty:
        result.fail("fact_orders vazia — não é possível validar sales_amount")
        return

    required_cols = {"quantity_ordered", "price_each", "sales_amount"}
    missing = required_cols - set(fact.columns)
    if missing:
        result.fail(f"Colunas ausentes em fact_orders: {missing}")
        return

    expected = fact["quantity_ordered"] * fact["price_each"]
    # Tolerância de 0.01 para arredondamento decimal
    mismatches = (fact["sales_amount"] - expected).abs() > 0.01
    n_mismatches = mismatches.sum()

    if n_mismatches == 0:
        result.ok(
            f"sales_amount = quantity_ordered × price_each em todos os "
            f"{len(fact)} registros"
        )
    else:
        result.fail(
            f"{n_mismatches} registro(s) com sales_amount inconsistente "
            f"(de {len(fact)} total)"
        )
        bad = fact[mismatches].head(3)
        for _, row in bad.iterrows():
            print(
                f"    → order_id={row.get('order_id')}, "
                f"qty={row['quantity_ordered']}, "
                f"price={row['price_each']}, "
                f"sales={row['sales_amount']}, "
                f"expected={row['quantity_ordered'] * row['price_each']}"
            )


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Validação do ETL — Task 2")
    parser.add_argument(
        "--job-name",
        default=None,
        help="Nome do Glue Job (auto-detectado se omitido)",
    )
    parser.add_argument(
        "--bucket",
        default=None,
        help="Nome do bucket S3 de saída (auto-detectado se omitido)",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="Região AWS (default: us-east-1)",
    )
    args = parser.parse_args()

    # Auto-detect se não fornecido
    job_name = args.job_name or detect_job_name()
    bucket = args.bucket or detect_bucket(args.region)

    print("=" * 60)
    print("  Validação do Pipeline ETL — Task 2")
    print("=" * 60)
    print(f"  Job:    {job_name}")
    print(f"  Bucket: {bucket}")
    print(f"  Region: {args.region}")

    s3_client = boto3.client("s3", region_name=args.region)
    glue_client = boto3.client("glue", region_name=args.region)
    result = ValidationResult()

    # Executar validações
    validate_job_status(glue_client, job_name, result)
    validate_parquet_exists(s3_client, bucket, result)
    tables = validate_referential_integrity(s3_client, bucket, result)
    validate_sales_amount(tables, result)

    # Resumo
    print("\n" + "=" * 60)
    print(f"  RESULTADO: {result.passed} passed, {result.failed} failed")
    if result.success:
        print("  🎉 Pipeline ETL validado com sucesso!")
    else:
        print("  ⚠️  Falhas encontradas:")
        for err in result.errors:
            print(f"    • {err}")
    print("=" * 60)

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
