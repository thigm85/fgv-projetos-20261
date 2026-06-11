"""
Registra no Glue Data Catalog as tabelas Parquet geradas na Task 2.
Execute uma vez antes do notebook (credenciais AWS configuradas).
"""

from pathlib import Path
import sys

import awswrangler as wr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import AWS_REGION, GLUE_DATABASE, S3_BUCKET, S3_CURATED_PREFIX

# Pasta S3 (Task 2) -> nome da tabela exigido na Task 3 / query.md
TABLES = {
    "fact_orders": "fact_orders",
    "dim_customers": "dim_customers",
    "dim_products": "dim_products",
    "dim_countries": "dim_countries",
    # ETL gravou dates_dim; no Athena a tabela deve chamar dim_dates
    "dim_dates": "dates_dim",
}


def main() -> None:
    base = f"s3://{S3_BUCKET}/{S3_CURATED_PREFIX}".rstrip("/")
    wr.catalog.create_database(name=GLUE_DATABASE, exist_ok=True)

    for table_name, s3_folder in TABLES.items():
        path = f"{base}/{s3_folder}/"
        print(f"Registrando {table_name} <- {path}")
        columns_types, partitions_types = wr.s3.read_parquet_metadata(path=path)
        wr.catalog.create_parquet_table(
            database=GLUE_DATABASE,
            table=table_name,
            path=path,
            columns_types=columns_types,
            partitions_types=partitions_types,
            mode="overwrite",
        )

    print(f"Concluído. Database Glue/Athena: {GLUE_DATABASE} (região {AWS_REGION})")


if __name__ == "__main__":
    main()
