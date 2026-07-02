import os
import sys
import boto3
import pandas as pd
import logging
from dotenv import load_dotenv
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

JOB_NAME = "rds-to-s3-star-schema"
BUCKET_NAME = os.getenv("S3_BUCKET_NAME") 
PREFIX = "transformed_data"
REGION = "us-east-1"

def validate_etl():
    if not BUCKET_NAME:
        logger.error("ERRO: Defina a variável de ambiente S3_BUCKET_NAME.")
        return

    glue = boto3.client("glue", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)
    
    success = True

    logger.info(f"Passo 1/4: Tentando verificar status do Job '{JOB_NAME}'")
    try:
        runs = glue.get_job_runs(JobName=JOB_NAME, MaxResults=1)
        if runs["JobRuns"]:
            status = runs["JobRuns"][0]["JobRunState"]
            if status == "SUCCEEDED":
                logger.info(f"[OK] Job finalizado com status: {status}")
            else:
                logger.warning(f"[AVISO] Job em estado: {status}. Verifique se a execução terminou.")
        else:
            logger.warning("[AVISO] Nenhuma execução de Job encontrada.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'AccessDeniedException':
            logger.warning("[PULO] Permissão negada para consultar Glue Job. Validando apenas dados no S3...")
        else:
            logger.error(f"Erro ao acessar Glue: {e}")

    logger.info("Passo 2/4: Verificando arquivos Parquet no S3")
    tables = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]
    for table in tables:
        path = f"{PREFIX}/{table}/"
        try:
            objects = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=path)
            if "Contents" in objects and any(obj["Key"].endswith(".parquet") for obj in objects["Contents"]):
                logger.info(f"[OK] Arquivos Parquet encontrados para: {table}")
            else:
                logger.error(f"[FALHA] Saída Parquet não encontrada para: {table}")
                success = False
        except Exception as e:
            logger.error(f"Erro ao listar S3 para {table}: {e}")
            success = False

    if success:
        logger.info("Passo 3 & 4: Validando integridade e cálculo de sales_amount")
        try:
            fact_path = f"s3://{BUCKET_NAME}/{PREFIX}/fact_orders/"
            df_fact = pd.read_parquet(fact_path, storage_options={"key": os.getenv("AWS_ACCESS_KEY_ID"), 
                                                                 "secret": os.getenv("AWS_SECRET_ACCESS_KEY"),
                                                                 "token": os.getenv("AWS_SESSION_TOKEN")})
            
            if len(df_fact) == 0:
                logger.error("[FALHA] A tabela fato está vazia.")
                success = False
            else:
                logger.info(f"[OK] Tabela fato contém {len(df_fact)} registros.")

                df_fact["calc_sales"] = df_fact["quantity_ordered"].astype(float) * df_fact["price_each"].astype(float)
                diff = (df_fact["sales_amount"].astype(float) - df_fact["calc_sales"]).abs().max()
                
                if diff < 0.05:
                    logger.info("[OK] Cálculo de 'sales_amount' está consistente.")
                else:
                    logger.error(f"[FALHA] Inconsistência no cálculo de vendas. Diferença máx: {diff}")
                    success = False

                if df_fact["customer_id"].isnull().any() or df_fact["product_id"].isnull().any():
                    logger.error("[FALHA] Chaves nulas encontradas na tabela fato.")
                    success = False
                else:
                    logger.info("[OK] Chaves dimensionais preenchidas corretamente.")

        except Exception as e:
            logger.error(f"Erro ao ler/validar dados do S3: {e}")
            success = False

    if success:
        logger.info("\n>>> VALIDAÇÃO DA TASK 2 CONCLUÍDA COM SUCESSO! <<<")
        sys.exit(0)
    else:
        logger.error("\n>>> VALIDAÇÃO DA TASK 2 REPROVADA. <<<")
        sys.exit(1)

if __name__ == "__main__":
    validate_etl()
