import os
import sys
import subprocess
import boto3
import time
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def get_terraform_output(key):
    """Get a value from terraform output"""
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", key],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


GLUE_JOB_NAME = os.getenv("GLUE_JOB_NAME") or get_terraform_output("glue_job_name") or "classicmodels-etl-etl-job"
S3_BUCKET = os.getenv("S3_BUCKET") or get_terraform_output("s3_bucket_name")

glue = boto3.client("glue", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)

EXPECTED_TABLES = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]
failures = []


def log_ok(msg):
    print(f"[OK] {msg}")


def log_fail(msg):
    print(f"[FAIL] {msg}")
    failures.append(msg)


def check_job_not_running():
    """Check if a job is already running before starting a new one"""
    runs = glue.get_job_runs(JobName=GLUE_JOB_NAME, MaxResults=1)
    if runs["JobRuns"]:
        state = runs["JobRuns"][0]["JobRunState"]
        if state in ("STARTING", "RUNNING", "STOPPING"):
            print(f"Job already running (state: {state}). Waiting for it to finish...")
            run_id = runs["JobRuns"][0]["Id"]
            return wait_for_job(run_id)
    return None


def wait_for_job(run_id):
    """Wait for a job run to complete"""
    while True:
        status = glue.get_job_run(JobName=GLUE_JOB_NAME, RunId=run_id)
        state = status["JobRun"]["JobRunState"]
        print(f"  Status: {state}")

        if state in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"):
            return state
        time.sleep(30)


def start_and_wait_job():
    """Start the Glue job and wait for completion"""
    existing = check_job_not_running()
    if existing:
        return existing == "SUCCEEDED"

    response = glue.start_job_run(JobName=GLUE_JOB_NAME)
    run_id = response["JobRunId"]
    print(f"  Job started: {run_id}")

    state = wait_for_job(run_id)

    if state != "SUCCEEDED":
        run_info = glue.get_job_run(JobName=GLUE_JOB_NAME, RunId=run_id)
        error = run_info["JobRun"].get("ErrorMessage", "Unknown error")
        log_fail(f"Job finished with status: {state}. Error: {error}")
        return False

    log_ok("Job completed with status SUCCEEDED")
    return True


def validate_s3_output():
    """Check that all expected Parquet outputs exist in S3"""
    print("\n--- Validating S3 outputs ---")

    for table in EXPECTED_TABLES:
        prefix = f"output/{table}/"
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, MaxKeys=5)
        contents = response.get("Contents", [])
        parquet_files = [f for f in contents if f["Key"].endswith(".parquet")]

        if parquet_files:
            log_ok(f"{table}: {len(parquet_files)} parquet file(s)")
        else:
            log_fail(f"{table}: missing from S3")


def read_parquet_from_s3(table_name):
    """Download and read all parquet partitions for a table from S3"""
    import pandas as pd
    import io

    prefix = f"output/{table_name}/"
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    parquet_files = [f["Key"] for f in response.get("Contents", []) if f["Key"].endswith(".parquet")]

    if not parquet_files:
        return None

    frames = []
    for key in parquet_files:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        frames.append(pd.read_parquet(io.BytesIO(obj["Body"].read())))
    return pd.concat(frames, ignore_index=True)


def validate_fact_orders():
    """Validate fact_orders content and business rules"""
    print("\n--- Validating fact_orders content ---")

    try:
        import pandas as pd

        df = read_parquet_from_s3("fact_orders")
        if df is None:
            log_fail("No parquet files found for fact_orders")
            return

        print(f"  Rows: {len(df)}")
        print(f"  Columns: {list(df.columns)}")

        required_cols = ["order_id", "customer_id", "product_id", "order_date_key",
                         "country_key", "quantity_ordered", "price_each", "sales_amount"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            log_fail(f"Missing columns: {missing_cols}")
            return

        log_ok("All required columns present")

        if len(df) == 0:
            log_fail("fact_orders has 0 rows")
            return
        log_ok(f"fact_orders has {len(df)} rows")

        computed = df["quantity_ordered"] * df["price_each"]
        diff = (df["sales_amount"] - computed).abs().sum()
        if diff < 0.01:
            log_ok("sales_amount = quantity_ordered * price_each (consistent)")
        else:
            log_fail(f"sales_amount inconsistent (total diff={diff:.4f})")

    except ImportError:
        print("(pandas/pyarrow not installed, skipping content validation)")


def validate_referential_integrity():
    """Check that fact_orders keys reference valid dimension entries"""
    print("\n--- Validating referential integrity ---")

    try:
        import pandas as pd

        fact = read_parquet_from_s3("fact_orders")
        if fact is None:
            log_fail("Cannot validate integrity: fact_orders not found")
            return

        checks = {
            "dim_customers": ("customer_id", "customer_id"),
            "dim_products": ("product_id", "product_id"),
            "dim_dates": ("order_date_key", "date_key"),
            "dim_countries": ("country_key", "country_key"),
        }

        for dim_name, (fact_col, dim_col) in checks.items():
            dim = read_parquet_from_s3(dim_name)
            if dim is None:
                log_fail(f"{dim_name}: not found in S3")
                continue

            fact_keys = set(fact[fact_col].dropna().unique())
            dim_keys = set(dim[dim_col].dropna().unique())
            orphans = fact_keys - dim_keys

            if len(orphans) == 0:
                log_ok(f"{fact_col} -> {dim_name}.{dim_col}: all keys valid")
            else:
                log_fail(f"{fact_col} -> {dim_name}.{dim_col}: {len(orphans)} orphan key(s)")

    except ImportError:
        print("(pandas/pyarrow not installed, skipping content validation)")


if __name__ == "__main__":
    print("=" * 50)
    print("ETL pipeline validation")
    print("=" * 50)

    if not S3_BUCKET:
        print("S3_BUCKET not detected")
        sys.exit(1)

    print(f"Glue Job: {GLUE_JOB_NAME}")
    print(f"S3 Bucket: {S3_BUCKET}")

    print("\n--- Starting Glue Job ---")
    job_ok = start_and_wait_job()

    if job_ok:
        validate_s3_output()
        validate_fact_orders()
        validate_referential_integrity()

    print("\n" + "=" * 50)
    if failures:
        print(f"VALIDATION FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL VALIDATIONS PASSED")
        sys.exit(0)
