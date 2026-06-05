from __future__ import annotations

import logging
import sys
import time

import boto3

from common import configure_logging, load_environment, require_env


FINAL_FAILURE_STATES = {"FAILED", "STOPPED", "TIMEOUT", "ERROR"}
SUCCESS_STATE = "SUCCEEDED"


def main() -> int:
    configure_logging()
    load_environment()

    region = require_env("AWS_REGION")
    job_name = require_env("GLUE_JOB_NAME")

    glue = boto3.client("glue", region_name=region)
    response = glue.start_job_run(JobName=job_name)
    job_run_id = response["JobRunId"]
    logging.info("Glue job iniciado: %s", job_run_id)

    timeout_seconds = 60 * 30
    poll_interval = 30
    waited = 0

    while waited <= timeout_seconds:
        run = glue.get_job_run(JobName=job_name, RunId=job_run_id, PredecessorsIncluded=False)["JobRun"]
        state = run["JobRunState"]
        logging.info("Glue job %s em estado %s", job_run_id, state)

        if state == SUCCESS_STATE:
            logging.info("Glue job concluido com sucesso")
            return 0

        if state in FINAL_FAILURE_STATES:
            error_message = run.get("ErrorMessage", "Sem mensagem detalhada")
            logging.error("Glue job terminou com falha: %s", state)
            logging.error("Detalhe do erro: %s", error_message)
            return 1

        time.sleep(poll_interval)
        waited += poll_interval

    logging.error("Tempo limite excedido aguardando o Glue job")
    return 1


if __name__ == "__main__":
    sys.exit(main())
