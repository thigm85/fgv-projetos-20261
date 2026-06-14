import sys
import time
import argparse
import subprocess
import logging
import json
import boto3
import awswrangler as wr
import pandas as pd
from botocore.exceptions import ClientError

# Configurações de observabilidade
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("ETLOrchestrator")

# Carregando as configurações do pipeline
with open("config/etl_configs.json", "r") as f:
    etl_configs = json.load(f)

# Configurações do pipeline
JOB_NAME = etl_configs["job_name"]
REGION = etl_configs["region"]
BUCKET_NAME = etl_configs["bucket_name"]
BASE_PATH = f"s3://{BUCKET_NAME}/output"

def run_terraform(dry_run: bool):
    """
    Executa os comandos do Terraform.
    """
    try:
        logger.info("Passo 1/4 - Inicializando Terraform...")
        subprocess.run(["terraform", "init"], check = True, capture_output = True, text = True)

        if dry_run:
            logger.info("Passo 2/4 - Executando DRY-RUN do Terraform...")
            subprocess.run(["terraform", "plan"], check = True)
            logger.info("Dry-run concluído. O pipeline será abortado aqui por segurança.")
            sys.exit(0)
        else:
            logger.info("Passo 2/4 - Aplicando infraestrutura do Terraform...")
            subprocess.run(["terraform", "apply", "-auto-approve"], check = True)
            logger.info("Infraestrutura provisionada com sucesso.")

    except subprocess.CalledProcessError as e:
        logger.error(f"Falha na execução do Terraform. Código de saída: {e.returncode}")
        sys.exit(1)

def run_glue_job():
    """
    Dispara o Job do Glue e aguarda a conclusão com polling.
    """
    logger.info(f"Passo 3/4 - Iniciando o Job do Glue '{JOB_NAME}'...")

    # Criando o cliente do Glue
    glue_client = boto3.client("glue", region_name = REGION)

    # Disparando o Job
    try:
        response = glue_client.start_job_run(JobName = JOB_NAME)
        job_run_id = response["JobRunId"]

        logger.info(f"Job disparado com sucesso. (Run ID: {job_run_id}). Aguardando status SUCCEEDED...")

        # Loop de repetição para checar o status
        while True:
            status_response = glue_client.get_job_run(JobName = JOB_NAME, RunId = job_run_id)
            status = status_response["JobRun"]["JobRunState"]

            if status == "SUCCEEDED":
                logger.info("\nO Job finalizou com sucesso. Avançando para validação de dados...\n")
                break
            elif status in ["FAILED", "STOPPED", "TIMEOUT"]:
                error_msg = status_response["JobRun"].get("ErrorMessage", "Erro desconhecido.")
                logger.error(f"\nO Job falhou com status {status}. Mensagem de erro: {error_msg}")
                # Interrompe o script se der erro
                sys.exit(1)
            
            # Espera 20 segundos antes de perguntar para a AWS de novo
            logger.info(f"Status atual: {status}. Checando novamente em 20s...")
            time.sleep(20)

    except ClientError as e:
        logger.error(f"Erro ao interagir com o AWS Glue: {e}")
        sys.exit(1)

def validate_quality_gates() -> int:
    """
    Realiza a validação do ETL e retorna o exit code.
    """
    logger.info("Passo 4/4 - Iniciando validação de dados...")
    failures = 0

    # Checagem de arquivos
    expected_tables = ["dim_customers", "dim_products", "dim_dates", "dim_countries", "fact_orders"]

    for table in expected_tables:
        path = f"{BASE_PATH}/{table}/"
        files = wr.s3.list_objects(path)

        if files:
            logger.info(f" -> Tabela encontrada: '{table}' ({len(files)} arquivo(s))")
        else:
            logger.error(f" -> Tabela faltando: '{table}'")
            failures += 1

    if failures > 0:
        return 1

    df_fact = wr.s3.read_parquet(f"{BASE_PATH}/fact_orders/")
    df_dim_prod = wr.s3.read_parquet(f"{BASE_PATH}/dim_products/")
    df_dim_cust = wr.s3.read_parquet(f"{BASE_PATH}/dim_customers/")

    # Verificando se a tabela fato contém registros
    if not df_fact.empty:
        logger.info(f" -> Tabela fato populada ({len(df_fact)} registros).")
    else:
        logger.error(" -> fact_orders está vazia!")
        failures += 1

    # Verificando as referências a chaves válidas das dimensões

    # Transformando as colunas de ID em sets para cruzar os dados
    products_fact = set(df_fact["product_id"])
    products_dim = set(df_dim_prod["product_id"])

    invalid_products = products_fact - products_dim

    if len(invalid_products) == 0:
        logger.info(" -> Integridade OK: Todos os product_id são válidos.")
    else:
        logger.error(f" -> Referência inválida: {len(invalid_products)} product_id órfãos.")
        failures += 1

    clients_fact = set(df_fact["customer_id"])
    clients_dim = set(df_dim_cust["customer_id"])

    invalid_clients = clients_fact - clients_dim

    if len(invalid_clients) == 0:
        logger.info(" -> Integridade OK: Todos os customer_id são válidos.")
    else:
        logger.error(f" -> Referência inválida: {len(invalid_clients)} customer_id órfãos.")
        failures += 1

    # Verificando a consistência do sales_amount

    # Forçando a conversão para tipo numérico
    df_fact["quantity_ordered"] = pd.to_numeric(df_fact["quantity_ordered"])
    df_fact["price_each"] = pd.to_numeric(df_fact["price_each"])
    df_fact["sales_amount"] = pd.to_numeric(df_fact["sales_amount"])

    # Recalculando localmente
    df_fact["sales_amount_calc"] = (df_fact["quantity_ordered"] * df_fact["price_each"]).round(2)
    df_fact["sales_amount_round"] = df_fact["sales_amount"].round(2)

    # Filtrando linhas onde o cálculo refeito é diferente do valor que veio do Parquet
    divergences = df_fact[df_fact["sales_amount_round"] != df_fact["sales_amount_calc"]]

    if divergences.empty:
        logger.info(" -> Regra de negócio OK: sales_amount consistente em toda a base.")
    else:
        logger.error(f" -> {len(divergences)} inconsistências no sales_amount.")
        failures += 1

    return 1 if failures > 0 else 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Orquestrador do ETL")
    parser.add_argument("--dry-run", action = "store_true", help = "Simula a criação da infraestrutura sem alterar recursos")
    args = parser.parse_args()

    logger.info("=== INICIANDO ETL DE DADOS ===")

    # Executa o Terraform
    run_terraform(args.dry_run)

    # Executa o ETL
    run_glue_job()

    # Valida os dados
    exit_code = validate_quality_gates()

    if exit_code == 0:
        logger.info("=== ETL CONCLUÍDO COM SUCESSO ===")
        sys.exit(0)
    else:
        logger.error("=== PIPELINE ABORTADO: FALHA NOS DADOS ===")
        sys.exit(1)