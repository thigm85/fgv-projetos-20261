from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3
import pymysql
from dotenv import dotenv_values
from pymysql.err import OperationalError


TASK_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TASK_DIR.parents[1]
ENV_PATH = TASK_DIR / ".env"
TERRAFORM_DIR = TASK_DIR / "terraform"
SQL_FILE = REPO_ROOT / "assignment_1" / "task_1" / "data" / "mysqlsampledatabase.sql"
RUN_LOG = TASK_DIR / "evidence" / "run_log.md"

PIPELINE_NAME = "classicmodels_sales"


def load_task_env() -> dict[str, str]:
    values = {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}
    os.environ.update(values)
    return values


def terraform_outputs() -> dict[str, Any]:
    result = subprocess.run(
        ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-json"],
        check=True,
        text=True,
        capture_output=True,
    )
    raw_outputs = json.loads(result.stdout)
    return {name: item["value"] for name, item in raw_outputs.items()}


def split_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    delimiter = ";"

    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        if stripped.upper().startswith("DELIMITER"):
            delimiter = stripped.split()[1]
            continue

        current.append(line)
        if stripped.endswith(delimiter):
            statement = "\n".join(current).strip()
            if delimiter != ";":
                statement = statement[: statement.rfind(delimiter)].strip()
            if statement:
                statements.append(statement)
            current = []

    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)

    return statements


def connect_mysql(host: str, password: str, database: str | None = None):
    return pymysql.connect(
        host=host,
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "admin"),
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=10,
        read_timeout=120,
        write_timeout=120,
    )


def connect_with_retry(host: str, password: str, database: str | None = None):
    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            return connect_mysql(host, password, database)
        except OperationalError as exc:
            last_error = exc
            print(f"[mysql] waiting for RDS ({attempt}/30): {exc}")
            time.sleep(10)
    raise RuntimeError("Could not connect to RDS MySQL") from last_error


def database_has_orders(host: str, password: str) -> bool:
    try:
        connection = connect_mysql(host, password, os.getenv("DB_NAME", "classicmodels"))
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM orders")
            total = cursor.fetchone()["total"]
        connection.close()
        return total > 0
    except Exception:
        return False


def load_classicmodels(host: str, password: str) -> None:
    if database_has_orders(host, password):
        print("[mysql] classicmodels already loaded")
        return

    if not SQL_FILE.exists():
        raise FileNotFoundError(f"Missing SQL file: {SQL_FILE}")

    statements = split_statements(SQL_FILE.read_text(encoding="utf-8", errors="ignore"))
    connection = connect_with_retry(host, password)
    print(f"[mysql] loading classicmodels from {SQL_FILE}")

    try:
        with connection.cursor() as cursor:
            for index, statement in enumerate(statements, start=1):
                cursor.execute(statement)
                if index % 50 == 0 or index == len(statements):
                    print(f"[mysql] executed {index}/{len(statements)} statements")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_watermark(host: str, password: str) -> date:
    connection = connect_with_retry(host, password, os.getenv("DB_NAME", "classicmodels"))
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS etl_watermark (
                    pipeline_name VARCHAR(64) PRIMARY KEY,
                    last_processed_order_date DATE,
                    last_run_at DATETIME NULL,
                    last_run_status VARCHAR(32) NOT NULL
                )
                """
            )
            cursor.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
            max_order_date = cursor.fetchone()["max_order_date"]
            if max_order_date is None:
                raise RuntimeError("orders is empty; cannot initialize watermark")

            cursor.execute(
                """
                INSERT INTO etl_watermark (
                    pipeline_name,
                    last_processed_order_date,
                    last_run_at,
                    last_run_status
                )
                VALUES (%s, %s, NULL, 'NEVER_RUN')
                ON DUPLICATE KEY UPDATE
                    last_processed_order_date = COALESCE(
                        last_processed_order_date,
                        VALUES(last_processed_order_date)
                    ),
                    last_run_status = COALESCE(last_run_status, 'NEVER_RUN')
                """,
                (PIPELINE_NAME, max_order_date),
            )
        connection.commit()
        print(f"[mysql] watermark ready at {max_order_date}")
        return max_order_date
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def next_business_day(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def simulate_orders(host: str, password: str, count: int = 5, seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    connection = connect_with_retry(host, password, os.getenv("DB_NAME", "classicmodels"))

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT last_processed_order_date
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (PIPELINE_NAME,),
            )
            watermark = cursor.fetchone()["last_processed_order_date"]

            cursor.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
            max_order_date = cursor.fetchone()["max_order_date"]
            current_date = max(value for value in [watermark, max_order_date] if value is not None)

            cursor.execute("SELECT MAX(orderNumber) AS max_order_number FROM orders")
            order_number = int(cursor.fetchone()["max_order_number"]) + 1

            cursor.execute("SELECT customerNumber FROM customers")
            customers = [row["customerNumber"] for row in cursor.fetchall()]

            cursor.execute("SELECT productCode, MSRP, buyPrice FROM products")
            products = list(cursor.fetchall())

            created_orders: list[int] = []
            created_dates: list[date] = []
            details_count = 0

            for offset in range(count):
                current_date = next_business_day(current_date)
                current_order_number = order_number + offset
                customer_number = rng.choice(customers)

                cursor.execute(
                    """
                    INSERT INTO orders (
                        orderNumber,
                        orderDate,
                        requiredDate,
                        shippedDate,
                        status,
                        comments,
                        customerNumber
                    )
                    VALUES (%s, %s, %s, NULL, 'In Process', %s, %s)
                    """,
                    (
                        current_order_number,
                        current_date,
                        current_date + timedelta(days=7),
                        "Simulated order for Task 2 incremental run",
                        customer_number,
                    ),
                )

                selected_products = rng.sample(products, rng.randint(1, min(3, len(products))))
                for line_number, product in enumerate(selected_products, start=1):
                    price = product["MSRP"] or product["buyPrice"] or Decimal("1.00")
                    cursor.execute(
                        """
                        INSERT INTO orderdetails (
                            orderNumber,
                            productCode,
                            quantityOrdered,
                            priceEach,
                            orderLineNumber
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            current_order_number,
                            product["productCode"],
                            rng.randint(1, 20),
                            Decimal(str(price)).quantize(Decimal("0.01")),
                            line_number,
                        ),
                    )
                    details_count += 1

                created_orders.append(current_order_number)
                created_dates.append(current_date)

        connection.commit()
        print(f"[mysql] simulated orders: {created_orders}")
        return {
            "orders": created_orders,
            "start_date": min(created_dates),
            "end_date": max(created_dates),
            "details_count": details_count,
            "previous_watermark": watermark,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def start_and_wait_for_glue_job(job_name: str) -> dict[str, str]:
    glue = boto3.client("glue", region_name=os.getenv("AWS_REGION", "us-east-1"))
    response = glue.start_job_run(JobName=job_name)
    run_id = response["JobRunId"]
    print(f"[glue] started job run: {run_id}")

    terminal_states = {"SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"}
    while True:
        run = glue.get_job_run(JobName=job_name, RunId=run_id, PredecessorsIncluded=False)["JobRun"]
        state = run["JobRunState"]
        print(f"[glue] state={state}")
        if state in terminal_states:
            return {"run_id": run_id, "state": state}
        time.sleep(30)


def read_watermark(host: str, password: str) -> Any:
    connection = connect_with_retry(host, password, os.getenv("DB_NAME", "classicmodels"))
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT last_processed_order_date, last_run_status
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (PIPELINE_NAME,),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def append_run_log(outputs: dict[str, Any], simulation: dict[str, Any], glue_run: dict[str, str], watermark: Any):
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n"
            f"## Automated run - {timestamp}\n\n"
            f"- Glue Job: `{outputs['glue_job_name']}`\n"
            f"- Glue Job Run ID: `{glue_run['run_id']}`\n"
            f"- Glue Job State: `{glue_run['state']}`\n"
            f"- S3 bucket: `{outputs['s3_bucket_name']}`\n"
            f"- Glue database: `{outputs['glue_database_name']}`\n"
            f"- Previous watermark: `{simulation['previous_watermark']}`\n"
            f"- Simulated orders: `{simulation['orders']}`\n"
            f"- Simulated date range: `{simulation['start_date']} to {simulation['end_date']}`\n"
            f"- Simulated orderdetails rows: `{simulation['details_count']}`\n"
            f"- Watermark after run: `{watermark}`\n"
        )


def main() -> int:
    load_task_env()
    outputs = terraform_outputs()
    host = outputs["rds_endpoint"]
    password = os.getenv("TF_VAR_db_password") or os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError("Missing DB password in .env")

    load_classicmodels(host, password)
    initialize_watermark(host, password)
    simulation = simulate_orders(host, password)
    glue_run = start_and_wait_for_glue_job(outputs["glue_job_name"])
    watermark = read_watermark(host, password)
    append_run_log(outputs, simulation, glue_run, watermark)

    if glue_run["state"] != "SUCCEEDED":
        return 1

    print("[task2] completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
