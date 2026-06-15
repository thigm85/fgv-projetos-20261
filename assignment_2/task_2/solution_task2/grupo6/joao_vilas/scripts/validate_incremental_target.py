from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
import time

import boto3

from config import load_settings
from db import connect_mysql


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

PARTITION_RE = re.compile(r"fact_orders/order_year=\d+/order_month=\d+/")


def terraform_output(name: str) -> str:
    result = subprocess.run(
        ["terraform", "-chdir=terraform", "output", "-raw", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def check_watermark(settings) -> list[str]:
    failures: list[str] = []
    conn = connect_mysql(settings)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT last_processed_order_date, last_run_status
                FROM etl_watermark WHERE pipeline_name = %s
                """,
                (settings.pipeline_name,),
            )
            row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return [f"Watermark '{settings.pipeline_name}' não encontrado."]

    logger.info("Watermark: status=%s, data=%s", row["last_run_status"], row["last_processed_order_date"])
    if row["last_run_status"] != "SUCCEEDED":
        failures.append(f"last_run_status = {row['last_run_status']} (esperado SUCCEEDED).")
    if row["last_processed_order_date"] is None:
        failures.append("last_processed_order_date está NULL.")
    return failures


def check_partitions(bucket: str, output_prefix: str) -> list[str]:
    s3 = boto3.client("s3")
    prefix = f"{output_prefix.rstrip('/')}/fact_orders/"
    paginator = s3.get_paginator("list_objects_v2")

    partitions = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            match = PARTITION_RE.search(obj["Key"])
            if match:
                partitions.add(match.group(0))

    if not partitions:
        return [f"Nenhuma partição Hive-style encontrada em s3://{bucket}/{prefix}"]

    logger.info("Partições encontradas (%s):", len(partitions))
    for part in sorted(partitions):
        logger.info("  %s", part)
    return []


def run_athena_count(database: str, workgroup: str, region: str) -> list[str]:
    client = boto3.client("athena", region_name=region)
    query = "SELECT COUNT(*) AS total FROM fact_orders"

    start = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )
    qid = start["QueryExecutionId"]

    while True:
        execution = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = execution["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(2)

    if state != "SUCCEEDED":
        reason = execution["Status"].get("StateChangeReason", "")
        return [f"Athena COUNT(*) falhou: {state} {reason}"]

    result = client.get_query_results(QueryExecutionId=qid)
    total = int(result["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"])
    logger.info("Athena COUNT(*) fact_orders = %s", total)
    return [] if total > 0 else ["Athena retornou 0 linhas em fact_orders."]


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida o alvo após o ETL incremental")
    parser.add_argument("--athena", action="store_true", help="Inclui COUNT(*) via Athena")
    args = parser.parse_args()

    settings = load_settings()
    bucket = terraform_output("etl_bucket_name")
    output_prefix = terraform_output("analytics_prefix")

    failures: list[str] = []
    failures += check_watermark(settings)
    failures += check_partitions(bucket, output_prefix)

    if args.athena:
        database = terraform_output("glue_database")
        workgroup = terraform_output("athena_workgroup")
        failures += run_athena_count(database, workgroup, settings.aws_region)

    if failures:
        logger.error("Validação do alvo falhou com %s erro(s):", len(failures))
        for failure in failures:
            logger.error("- %s", failure)
        return 1

    logger.info("Validação do alvo concluída com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
