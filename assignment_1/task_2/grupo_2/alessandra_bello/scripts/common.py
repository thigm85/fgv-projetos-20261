from __future__ import annotations

import logging
import os
import json
import subprocess
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
TERRAFORM_DIR = BASE_DIR / "terraform"
DEFAULT_ENV = {
    "AWS_REGION": "us-east-1",
    "DB_PORT": "3306",
    "DB_NAME": "classicmodels",
    "DB_USER": "admin",
    "DB_PASSWORD": "ClassicModels123!",
    "GLUE_JOB_NAME": "classicmodels-etl-job",
}


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_environment() -> None:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)


def terraform_output(name: str) -> str | None:
    if not TERRAFORM_DIR.exists():
        return None

    try:
        result = subprocess.run(
            ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    try:
        outputs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    payload = outputs.get(name)
    if not isinstance(payload, dict):
        return None

    value = payload.get("value")
    if value in (None, ""):
        return None
    return str(value)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value

    terraform_fallbacks = {
        "DB_HOST": "rds_endpoint",
        "GLUE_JOB_NAME": "glue_job_name",
        "S3_BUCKET_NAME": "analytics_bucket_name",
    }
    output_name = terraform_fallbacks.get(name)
    if output_name:
        output_value = terraform_output(output_name)
        if output_value:
            return output_value

    default_value = DEFAULT_ENV.get(name)
    if default_value:
        return default_value

    raise RuntimeError(f"Missing required environment variable: {name}")
