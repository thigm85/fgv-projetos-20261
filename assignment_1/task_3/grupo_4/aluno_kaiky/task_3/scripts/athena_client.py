"""Cliente Athena via AWS Data Wrangler."""

from __future__ import annotations

import os

import awswrangler as wr
import boto3
import pandas as pd

from scripts.queries import (
    AWS_REGION,
    GLUE_DATABASE,
    SQL_DIM_PRODUCTS,
    SQL_SALES_BY_COUNTRY,
    SQL_SALES_DETAIL,
)


def resolve_aws_region() -> str:
    """Região AWS: env (AWS_REGION / AWS_DEFAULT_REGION) ou queries.AWS_REGION."""
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or AWS_REGION
    )


def get_boto3_session() -> boto3.Session:
    """Sessão boto3 com região explícita (evita NoRegionError no awswrangler)."""
    return boto3.Session(region_name=resolve_aws_region())


def read_sql_query(
    sql: str,
    database: str = GLUE_DATABASE,
) -> pd.DataFrame:
    """Executa SQL no Athena e retorna um DataFrame."""
    kwargs: dict = {
        "sql": sql,
        "database": database,
        "boto3_session": get_boto3_session(),
    }
    s3_output = os.environ.get("ATHENA_S3_OUTPUT")
    if s3_output:
        kwargs["s3_output"] = s3_output
    return wr.athena.read_sql_query(**kwargs)


def load_dim_products(database: str = GLUE_DATABASE) -> pd.DataFrame:
    """4.2 — Consulta exploratória em dim_products."""
    return read_sql_query(SQL_DIM_PRODUCTS, database=database)


def load_sales_by_country(database: str = GLUE_DATABASE) -> pd.DataFrame:
    """4.3 — Vendas totais por país."""
    return read_sql_query(SQL_SALES_BY_COUNTRY, database=database)


def load_sales_detail(database: str = GLUE_DATABASE) -> pd.DataFrame:
    """4.4 — Detalhamento por data, linha, produto e país."""
    df = read_sql_query(SQL_SALES_DETAIL, database=database)
    df["full_date"] = pd.to_datetime(df["full_date"])
    return df


def preview_queries() -> None:
    """Executa as três consultas e imprime prévias."""
    print(f"Região: {resolve_aws_region()}")
    print(f"Database: {GLUE_DATABASE}\n")

    df_products = load_dim_products()
    print("=== dim_products ===")
    print(df_products.head(), "\n")

    df_country = load_sales_by_country()
    print("=== vendas por país ===")
    print(df_country, "\n")

    df_detail = load_sales_detail()
    print("=== detalhamento ===")
    print(df_detail.head())


if __name__ == "__main__":
    preview_queries()
