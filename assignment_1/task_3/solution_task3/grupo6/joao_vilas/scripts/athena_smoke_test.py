from __future__ import annotations

import logging
import sys

import awswrangler as wr
import boto3

from config import load_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


QUERIES = {
    "dim_products_preview": """
        SELECT product_id, product_name, product_line, product_vendor
        FROM dim_products
        LIMIT 20
    """,
    "sales_by_country": """
        SELECT
            dim_countries.country,
            SUM(fact_orders.sales_amount) AS total_sales
        FROM fact_orders
        JOIN dim_countries ON fact_orders.country_key = dim_countries.country_key
        GROUP BY dim_countries.country
        ORDER BY total_sales DESC
        LIMIT 10
    """,
    "sales_detail": """
        SELECT
            dim_dates.full_date,
            dim_products.product_line,
            dim_products.product_name,
            dim_countries.country,
            SUM(fact_orders.sales_amount) AS total_sales
        FROM fact_orders
        JOIN dim_products  ON fact_orders.product_id    = dim_products.product_id
        JOIN dim_countries ON fact_orders.country_key   = dim_countries.country_key
        JOIN dim_dates     ON fact_orders.order_date_key = dim_dates.date_key
        GROUP BY 1, 2, 3, 4
    """,
}


def main() -> int:
    config = load_config()

    boto3.setup_default_session(region_name=config.aws_region)

    failures: list[str] = []

    for name, query in QUERIES.items():
        logger.info("Executando query: %s", name)

        try:
            df = wr.athena.read_sql_query(
                sql=query,
                database=config.glue_database,
                workgroup=config.athena_workgroup,
                ctas_approach=False,
            )
        except Exception as exc:  # noqa: BLE001 - smoke test relata todas as falhas
            logger.exception("Query %s falhou: %s", name, exc)
            failures.append(name)
            continue

        logger.info("OK: %s retornou %s linhas", name, len(df))
        if len(df) == 0:
            failures.append(f"{name} sem linhas")

    if failures:
        logger.error("Smoke test falhou: %s", failures)
        return 1

    logger.info("Smoke test concluido com sucesso")
    return 0


if __name__ == "__main__":
    sys.exit(main())
