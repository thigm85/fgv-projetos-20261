#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import boto3
import pyarrow.dataset as ds
import pyarrow.fs as fs

from config_utils import configure_aws_env, load_env_config, section


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
EXPECTED_TABLES = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]


def run(args: list[str]) -> None:
    print("[run]", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def terraform_env(config) -> dict[str, str]:
    env = dict(os.environ)
    configure_aws_env(config)
    env.update(os.environ)
    rds = section(config, "rds")
    etl = section(config, "etl")
    endpoint = json.loads((CONFIG_DIR / "db_endpoint.json").read_text(encoding="utf-8"))
    env.update(
        {
            "TF_VAR_region": section(config, "default").get("region", "us-east-1"),
            "TF_VAR_bucket_name": etl["bucket_name"],
            "TF_VAR_job_name": etl["job_name"],
            "TF_VAR_output_prefix": etl.get("output_prefix", "output"),
            "TF_VAR_db_host": endpoint["host"],
            "TF_VAR_db_port": str(endpoint["port"]),
            "TF_VAR_db_name": endpoint["database"],
            "TF_VAR_db_user": rds["db_user"],
            "TF_VAR_db_password": rds["db_password"],
            "TF_VAR_db_security_group_id": endpoint["security_group_id"],
        }
    )
    return env


def terraform_output() -> dict:
    result = subprocess.run(["terraform", "output", "-json"], cwd=ROOT, check=True, text=True, capture_output=True)
    raw = json.loads(result.stdout)
    return {key: item["value"] for key, item in raw.items()}


def ensure_configs() -> None:
    if not (CONFIG_DIR / ".env").exists():
        raise FileNotFoundError("Missing config/.env. Copy config/.env.example and fill it.")


def start_and_wait_glue(job_name: str, region: str) -> str:
    glue = boto3.client("glue", region_name=region)
    run_id = glue.start_job_run(JobName=job_name)["JobRunId"]
    print(f"[glue] started {job_name} run {run_id}")
    while True:
        job_run = glue.get_job_run(JobName=job_name, RunId=run_id)["JobRun"]
        state = job_run["JobRunState"]
        print(f"[glue] status: {state}")
        if state == "SUCCEEDED":
            return run_id
        if state in {"FAILED", "STOPPED", "TIMEOUT", "ERROR"}:
            raise RuntimeError(f"Glue job failed: {state} {job_run.get('ErrorMessage', '')}")
        time.sleep(20)


def validate_parquet(bucket: str, prefix: str, region: str) -> None:
    s3 = boto3.client("s3", region_name=region)
    s3fs = fs.S3FileSystem(region=region)
    failures: list[str] = []
    loaded = {}
    for table in EXPECTED_TABLES:
        table_prefix = f"{prefix.strip('/')}/{table}/"
        response = s3.list_objects_v2(Bucket=bucket, Prefix=table_prefix)
        files = [item["Key"] for item in response.get("Contents", []) if item["Key"].endswith(".parquet")]
        if not files:
            failures.append(f"{table}: no parquet files")
            continue
        dataset = ds.dataset(f"{bucket}/{table_prefix}", filesystem=s3fs, format="parquet")
        arrow_table = dataset.to_table()
        loaded[table] = arrow_table
        print(f"[validate] {table}: {arrow_table.num_rows} rows, {len(files)} parquet files")
        if arrow_table.num_rows == 0:
            failures.append(f"{table}: empty")
    if set(loaded) == set(EXPECTED_TABLES):
        fact = loaded["fact_orders"]
        dim_customers = set(loaded["dim_customers"]["customer_id"].to_pylist())
        dim_products = set(loaded["dim_products"]["product_id"].to_pylist())
        dim_dates = set(loaded["dim_dates"]["date_key"].to_pylist())
        dim_countries = set(loaded["dim_countries"]["country_key"].to_pylist())
        checks = [
            ("customer_id", dim_customers),
            ("product_id", dim_products),
            ("order_date_key", dim_dates),
            ("country_key", dim_countries),
        ]
        for column, values in checks:
            missing = set(fact[column].to_pylist()) - values
            if missing:
                failures.append(f"fact_orders.{column}: orphan keys {list(missing)[:10]}")
        qty = fact["quantity_ordered"].to_pylist()
        price = fact["price_each"].to_pylist()
        amount = fact["sales_amount"].to_pylist()
        invalid_sales = sum(1 for q, p, a in zip(qty, price, amount) if round(float(q) * float(p), 2) != round(float(a), 2))
        if invalid_sales:
            failures.append(f"sales_amount invalid rows: {invalid_sales}")
    if failures:
        raise RuntimeError("; ".join(failures))
    print("[validate] ETL outputs validated successfully")


def main() -> int:
    parser = argparse.ArgumentParser(description="Grupo 5 Task 2 ETL orchestrator")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ensure_configs()
    config = load_env_config()
    configure_aws_env(config)
    etl_cfg = section(config, "etl")
    region = section(config, "default").get("region", "us-east-1")

    if args.dry_run:
        print("[dry-run] config/.env loaded")
        print(f"[dry-run] region={region}")
        print(f"[dry-run] job_name={etl_cfg['job_name']}")
        print(f"[dry-run] bucket_name={etl_cfg['bucket_name']}")
        return 0

    run([sys.executable, "1_create_rds.py"])
    run([sys.executable, "2_load_data.py"])
    run([sys.executable, "3_validate_data.py"])

    tf_env = terraform_env(config)
    subprocess.run(["terraform", "init"], cwd=ROOT, check=True, env=tf_env)
    subprocess.run(["terraform", "plan"], cwd=ROOT, check=True, env=tf_env)
    if args.dry_run:
        return 0
    subprocess.run(["terraform", "apply", "-auto-approve"], cwd=ROOT, check=True, env=tf_env)
    outputs = terraform_output()
    run_id = start_and_wait_glue(outputs["glue_job_name"], region)
    print(f"[glue] completed run {run_id}")
    bucket = outputs["bucket_name"]
    prefix = outputs["output_path"].split(f"s3://{bucket}/", 1)[1]
    validate_parquet(bucket, prefix, region)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
