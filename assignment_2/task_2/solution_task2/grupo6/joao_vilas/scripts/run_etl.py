from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time

import boto3

from config import load_settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

TERMINAL_STATES = {"SUCCEEDED", "FAILED", "ERROR", "STOPPED", "TIMEOUT"}


def terraform_output(name: str) -> str:
    result = subprocess.run(
        ["terraform", "-chdir=terraform", "output", "-raw", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def wait_for_run(client, job_name: str, run_id: str, poll_seconds: int = 15) -> str:
    logger.info("Aguardando job %s (run %s)", job_name, run_id)
    while True:
        response = client.get_job_run(JobName=job_name, RunId=run_id)
        state = response["JobRun"]["JobRunState"]
        logger.info("status: %s", state)
        if state in TERMINAL_STATES:
            error_message = response["JobRun"].get("ErrorMessage")
            if error_message:
                logger.error("Mensagem de erro do Glue: %s", error_message)
            return state
        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispara e acompanha o Glue Job incremental")
    parser.add_argument("--job-name", help="Override do nome do Glue Job")
    parser.add_argument("--no-wait", action="store_true", help="Apenas dispara, sem aguardar")
    args = parser.parse_args()

    settings = load_settings()
    job_name = args.job_name or terraform_output("glue_job_name")

    client = boto3.client("glue", region_name=settings.aws_region)

    logger.info("Disparando Glue Job: %s", job_name)
    run_id = client.start_job_run(JobName=job_name)["JobRunId"]
    logger.info("JobRunId: %s", run_id)

    if args.no_wait:
        return 0

    final_state = wait_for_run(client, job_name, run_id)
    if final_state == "SUCCEEDED":
        logger.info("Job concluído com SUCCEEDED")
        return 0

    logger.error("Job terminou com estado %s", final_state)
    return 1


if __name__ == "__main__":
    sys.exit(main())
