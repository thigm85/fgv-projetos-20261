from __future__ import annotations

import logging
import sys

import boto3

from common import configure_logging, load_environment, require_env


EXPECTED_PREFIXES = [
    "analytics/fact_orders/",
    "analytics/dim_customers/",
    "analytics/dim_products/",
    "analytics/dim_dates/",
    "analytics/dim_countries/",
]


def latest_job_state(glue_client, job_name: str) -> str:
    response = glue_client.get_job_runs(JobName=job_name, MaxResults=1)
    runs = response.get("JobRuns", [])
    if not runs:
        raise RuntimeError(f"Nenhuma execucao encontrada para o job {job_name}")
    return runs[0]["JobRunState"]


def prefix_has_parquet_files(s3_client, bucket: str, prefix: str) -> bool:
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    for item in response.get("Contents", []):
        if item["Key"].endswith(".parquet"):
            return True
    return False


def main() -> int:
    configure_logging()
    load_environment()

    region = require_env("AWS_REGION")
    bucket = require_env("S3_BUCKET_NAME")
    job_name = require_env("GLUE_JOB_NAME")

    glue = boto3.client("glue", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    state = latest_job_state(glue, job_name)
    logging.info("Ultimo estado do Glue job: %s", state)
    if state != "SUCCEEDED":
        logging.error("O Glue job nao finalizou com SUCCEEDED")
        return 1

    failures: list[str] = []
    for prefix in EXPECTED_PREFIXES:
        if not prefix_has_parquet_files(s3, bucket, prefix):
            failures.append(f"Prefixo sem arquivos Parquet: s3://{bucket}/{prefix}")
        else:
            logging.info("Saida validada em s3://%s/%s", bucket, prefix)

    if failures:
        for failure in failures:
            logging.error(failure)
        return 1

    logging.info("Validacao do pipeline concluida com sucesso")
    return 0


if __name__ == "__main__":
    sys.exit(main())
