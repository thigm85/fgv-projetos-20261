import boto3
import sys
import time
import logging
from botocore.exceptions import ClientError

# Configuração do logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def run_glue_job(job_name, region_name="us-east-1"):
    logging.info(f"Passo 1/3 - Inicializando o cliente do AWS Glue na região {region_name}...")
    try:
        glue_client = boto3.client("glue", region_name=region_name)
    except Exception as e:
        logging.error(f"Erro ao inicializar o cliente boto3: {e}")
        sys.exit(1)

    logging.info(f"Passo 2/3 - Disparando a execução automática do Job: {job_name}...")
    try:
        response = glue_client.start_job_run(JobName=job_name)
        job_run_id = response["JobRunId"]
        logging.info(f"Job disparado com sucesso! JobRunId: {job_run_id}")
    except ClientError as err:
        logging.error(f"Erro da AWS ao iniciar o Job: {err.response["Error"]["Message"]}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Erro inesperado ao iniciar o Job: {e}")
        sys.exit(1)

    logging.info("Passo 3/3 - Monitorando o ciclo de vida e execução do Job (Polling)...")
    
    while True:
        try:
            status_response = glue_client.get_job_run(JobName=job_name, RunId=job_run_id)
            status_final = status_response["JobRun"]["JobRunState"]
            
            logging.info(f"Status atual do Job: {status_final}")
            
            if status_final in ["SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT"]:
                break
                
            time.sleep(30)
        except ClientError as err:
            logging.error(f"Erro ao consultar o status do Job na AWS: {err.response["Error"]["Message"]}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Erro inesperado no monitoramento: {e}")
            sys.exit(1)

    # Critério de aceitação objetivo e Exit Code determinístico (Endereça o Gap 5)
    if status_final == "SUCCEEDED":
        logging.info("Execução do pipeline de ETL concluída com SUCESSO no S3!")
        sys.exit(0)
    else:
        logging.error(f"O pipeline de ETL falhou ou foi interrompido. Estado final: {status_final}")
        sys.exit(1)

if __name__ == "__main__":
    JOB_NAME = "classicmodels_etl_to_star_schema"
    run_glue_job(JOB_NAME)
