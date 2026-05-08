"""
Inicia o Glue ETL job e faz polling até SUCCEEDED ou FAILED.
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

import boto3

info_path = BASE_DIR / "pipeline_info.json"
if not info_path.exists():
    print("[ERRO] pipeline_info.json não encontrado. Execute 'terraform apply' primeiro.")
    sys.exit(1)

info          = json.loads(info_path.read_text())
GLUE_JOB_NAME = info["glue_job_name"]
AWS_REGION    = os.environ.get("AWS_REGION", "us-east-1")
POLL_INTERVAL = 30
TERMINAL      = {"SUCCEEDED", "FAILED", "STOPPED", "ERROR", "TIMEOUT"}

session = boto3.Session(
    aws_access_key_id     = os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"],
    aws_session_token     = os.environ.get("AWS_SESSION_TOKEN"),
    region_name           = AWS_REGION,
)
glue = session.client("glue")

print(f"Iniciando job: {GLUE_JOB_NAME}")
run_id = glue.start_job_run(JobName=GLUE_JOB_NAME)["JobRunId"]
print(f"Job run ID  : {run_id}")

while True:
    detail  = glue.get_job_run(JobName=GLUE_JOB_NAME, RunId=run_id)["JobRun"]
    state   = detail["JobRunState"]
    elapsed = detail.get("ExecutionTime", 0)
    print(f"  [{elapsed:>4}s] {state}")
    if state in TERMINAL:
        break
    time.sleep(POLL_INTERVAL)

if state == "SUCCEEDED":
    print(f"\nJob finalizado com SUCCEEDED.")
    sys.exit(0)
else:
    print(f"\nJob finalizado com {state}: {detail.get('ErrorMessage', '')}")
    sys.exit(1)
