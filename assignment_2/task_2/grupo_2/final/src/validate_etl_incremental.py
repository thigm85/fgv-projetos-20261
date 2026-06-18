"""
Validação mínima de um ciclo incremental (rascunho da Task 3).

Cobre a tabela "Validação técnica sugerida (pré-Task 3)":
  1. Glue run -> SUCCEEDED
  2. Novos objetos sob analytics/fact_orders/order_year=.../order_month=.../
  3. etl_watermark.last_processed_order_date avançou em relação a --prev-watermark
  4. Athena: SELECT COUNT(*) FROM fact_orders WHERE order_year = ... retorna linhas
  5. sales_amount == quantity_ordered * price_each na partição tocada

Uso:
    python validate_etl_incremental.py --prev-watermark 2026-05-25 \
        --order-year 2026 --order-month 5

Exit code: 0 = tudo ok, 1 = alguma falha.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date
from io import BytesIO

import boto3
import mysql.connector
import pandas as pd

import envlocal

envlocal.load()

JOB_NAME = os.environ.get("GLUE_JOB_NAME", "classicmodels-etl-job")
S3_BUCKET = os.environ["S3_BUCKET"]
GLUE_DATABASE = os.environ["GLUE_DATABASE"]
ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
ATHENA_OUTPUT = os.environ["ATHENA_OUTPUT_LOCATION"]
SECRET_ARN = os.environ["SECRET_ARN"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "projetos")
PIPELINE_NAME = "classicmodels_sales"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("validate_incremental")

failures: list[str] = []


def ok(msg: str) -> None:
    log.info("  [ok]   %s", msg)


def fail(msg: str) -> None:
    log.error("  [FAIL] %s", msg)
    failures.append(msg)


def check_job_status(glue) -> str | None:
    log.info("=== 1. Glue job status ===")
    runs = glue.get_job_runs(JobName=JOB_NAME, MaxResults=1)["JobRuns"]
    if not runs:
        fail("Nenhum run encontrado para o job")
        return None
    last = runs[0]
    state = last["JobRunState"]
    run_id = last["Id"]
    if state == "SUCCEEDED":
        ok(f"Job {run_id} -> {state}")
        return run_id
    fail(f"Job {run_id} -> {state} (esperado SUCCEEDED)")
    return run_id


def check_new_partition_objects(s3, order_year: int, order_month: int) -> list[str]:
    log.info("=== 2. Objetos em fact_orders/order_year=%s/order_month=%s/ ===", order_year, order_month)
    prefix = f"analytics/fact_orders/order_year={order_year}/order_month={order_month}/"
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
    if keys:
        ok(f"{len(keys)} arquivo(s) parquet em s3://{S3_BUCKET}/{prefix}")
    else:
        fail(f"nenhum parquet em s3://{S3_BUCKET}/{prefix}")
    return keys


def check_watermark(prev_watermark: date) -> tuple[date | None, str | None]:
    log.info("=== 3. etl_watermark avançou ===")
    sm = boto3.client("secretsmanager", region_name=REGION)
    secret = json.loads(sm.get_secret_value(SecretId=SECRET_ARN)["SecretString"])
    conn = mysql.connector.connect(
        host=secret["host"], user=secret["username"], password=secret["password"],
        port=int(secret["port"]), database="classicmodels", use_pure=True, connection_timeout=10,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT last_processed_order_date, last_run_status FROM etl_watermark "
            "WHERE pipeline_name = %s",
            (PIPELINE_NAME,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        fail("etl_watermark: registro não encontrado")
        return None, None

    new_watermark, status = row
    if status != "SUCCEEDED":
        fail(f"last_run_status = {status} (esperado SUCCEEDED)")
    if new_watermark is not None and new_watermark > prev_watermark:
        ok(f"last_processed_order_date: {prev_watermark} -> {new_watermark}")
    elif new_watermark == prev_watermark:
        fail(f"last_processed_order_date não avançou (continua {new_watermark})")
    else:
        fail(f"last_processed_order_date inesperado: {new_watermark}")
    return new_watermark, status


def check_athena_count(athena, order_year: int, order_month: int | None) -> int | None:
    log.info("=== 4. Athena: COUNT(*) FROM fact_orders WHERE order_year = %s ===", order_year)
    where = f"order_year = {order_year}"
    if order_month is not None:
        where += f" AND order_month = {order_month}"
    query = f"SELECT COUNT(*) AS n FROM fact_orders WHERE {where}"

    exec_id = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": GLUE_DATABASE},
        WorkGroup=ATHENA_WORKGROUP,
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )["QueryExecutionId"]

    for _ in range(30):
        status = athena.get_query_execution(QueryExecutionId=exec_id)["QueryExecution"]["Status"]
        state = status["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    else:
        fail("Athena: timeout aguardando query")
        return None

    if state != "SUCCEEDED":
        fail(f"Athena query {state}: {status.get('StateChangeReason')}")
        return None

    rows = athena.get_query_results(QueryExecutionId=exec_id)["ResultSet"]["Rows"]
    n = int(rows[1]["Data"][0]["VarCharValue"])
    if n > 0:
        ok(f"{query} -> {n} linha(s)")
    else:
        fail(f"{query} -> 0 linhas")
    return n


def check_sales_amount(s3, keys: list[str]) -> None:
    log.info("=== 5. Regra sales_amount == quantity_ordered * price_each (partição nova) ===")
    if not keys:
        fail("sem parquet para validar a regra")
        return
    frames = []
    for key in keys:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        frames.append(pd.read_parquet(BytesIO(obj["Body"].read())))
    df = pd.concat(frames, ignore_index=True)
    expected = (df["quantity_ordered"] * df["price_each"]).round(2)
    actual = df["sales_amount"].round(2)
    mismatch = (expected - actual).abs() > 0.01
    n_bad = int(mismatch.sum())
    if n_bad == 0:
        ok(f"sales_amount consistente em {len(df)} registro(s)")
    else:
        fail(f"sales_amount inconsistente em {n_bad} registro(s)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prev-watermark", required=True, help="last_processed_order_date ANTES deste run (YYYY-MM-DD)")
    parser.add_argument("--order-year", type=int, required=True)
    parser.add_argument("--order-month", type=int, required=True)
    args = parser.parse_args()

    prev_watermark = date.fromisoformat(args.prev_watermark)

    log.info("Profile=%s Region=%s Bucket=%s", PROFILE, REGION, S3_BUCKET)
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    glue = session.client("glue")
    s3 = session.client("s3")
    athena = session.client("athena")

    check_job_status(glue)
    keys = check_new_partition_objects(s3, args.order_year, args.order_month)
    check_watermark(prev_watermark)
    check_athena_count(athena, args.order_year, args.order_month)
    check_sales_amount(s3, keys)

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
