import boto3
import pandas as pd
import sys
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [S3/Pandas] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("DataQuality")

def get_dynamic_bucket_name():
    file_path = os.path.join(os.path.dirname(__file__), 'bucket_name.txt')
    try:
        with open(file_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("Arquivo bucket_name.txt não encontrado. Execute o Terraform primeiro.")
        sys.exit(1)

BUCKET_NAME = get_dynamic_bucket_name()
REGION = 'us-east-1'

def validate_etl():
    logger.info("Iniciando bateria de validação do pipeline de dados (Task 2).")
    failed_tests = 0
    s3 = boto3.client('s3', region_name=REGION)

    # Validação Estrutural (S3)
    logger.info("Etapa 1/2: Validação da infraestrutura e objetos no S3.")
    tabelas_esperadas = ['fact_orders', 'dim_customers', 'dim_products', 'dim_dates', 'dim_countries']
    
    for tabela in tabelas_esperadas:
        try:
            response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f"{tabela}/")
            if 'Contents' in response and any(obj['Key'].endswith('.parquet') for obj in response['Contents']):
                logger.info(f"[PASS] Artefatos localizados para a tabela {tabela}.")
            else:
                logger.error(f"[FAIL] Ausência de arquivos .parquet para a tabela {tabela}.")
                failed_tests += 1
        except Exception as e:
            logger.error(f"[FAIL] Erro ao consultar bucket S3 para {tabela}: {e}")
            failed_tests += 1

    if failed_tests > 0:
        logger.error("Falha na etapa de infraestrutura. Abortando validação de dados em memória.")
        sys.exit(1)

    # Validação de Dados (Pandas)
    logger.info("Etapa 2/2: Validação de Qualidade e Integridade de Dados.")
    try:
        df_fact = pd.read_parquet(f"s3://{BUCKET_NAME}/fact_orders/")
        df_dim_cust = pd.read_parquet(f"s3://{BUCKET_NAME}/dim_customers/")
        df_dim_prod = pd.read_parquet(f"s3://{BUCKET_NAME}/dim_products/")

        if len(df_fact) == 0:
            logger.error("[FAIL] A tabela fato não contém registros.")
            failed_tests += 1
        else:
            logger.info(f"[PASS] Tabela fato validada: {len(df_fact)} registros extraídos.")

        clientes_invalidos = df_fact[~df_fact['customer_id'].isin(df_dim_cust['customer_id'])]
        if not clientes_invalidos.empty:
            logger.error(f"[FAIL] {len(clientes_invalidos)} ocorrências de integridade referencial quebrada (customer_id).")
            failed_tests += 1

        math_check = abs(df_fact['sales_amount'] - (df_fact['quantity_ordered'] * df_fact['price_each'])) < 0.01
        erros_matematicos = (~math_check).sum()
        if erros_matematicos > 0:
            logger.error(f"[FAIL] {erros_matematicos} ocorrências de falha na regra de negócio (sales_amount).")
            failed_tests += 1
        else:
            logger.info("[PASS] Integridade matemática da coluna 'sales_amount' validada com sucesso.")

    except Exception as e:
        logger.error(f"[CRITICAL] Falha na execução analítica do Pandas: {e}")
        sys.exit(1)

    # Conclusão
    if failed_tests == 0:
        logger.info("RESULTADO: Pipeline aprovado. Zero discrepâncias identificadas.")
        sys.exit(0)
    else:
        logger.error(f"RESULTADO: Pipeline reprovado. Total de falhas: {failed_tests}.")
        sys.exit(1)

if __name__ == "__main__":
    validate_etl()