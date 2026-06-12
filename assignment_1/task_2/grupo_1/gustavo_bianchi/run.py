import boto3
import time
import sys
import logging
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [AWS Glue] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ETL_Orchestrator")

def run_glue_job():
    glue = boto3.client('glue', region_name='us-east-1')
    job_name = "classicmodels-star-schema-job"

    try:
        logger.info(f"Disparando execução do Job: {job_name}")
        response = glue.start_job_run(JobName=job_name)
        run_id = response['JobRunId']
        logger.info(f"Job iniciado com sucesso. ID da Execução: {run_id}")

        # Polling para acompanhamento do status
        while True:
            status_response = glue.get_job_run(JobName=job_name, RunId=run_id)
            state = status_response['JobRun']['JobRunState']

            if state == 'SUCCEEDED':
                logger.info("Execução finalizada com SUCESSO.")
                sys.exit(0)
            elif state in ['FAILED', 'TIMEOUT', 'STOPPED']:
                error_msg = status_response['JobRun'].get('ErrorMessage', 'Sem detalhes de erro na API.')
                logger.error(f"Falha na execução. Status final: {state}. Detalhes: {error_msg}")
                sys.exit(1)

            logger.info(f"Status atual: {state}. Aguardando 30 segundos...")
            time.sleep(30)

    except ClientError as e:
        logger.error(f"Erro de comunicação/permissão com a API da AWS: {e.response['Error']['Message']}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado durante a orquestração: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_glue_job()