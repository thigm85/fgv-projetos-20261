import boto3
import pandas as pd
import io
import sys
import json
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_s3_bucket():
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            capture_output=True, text=True, check=True, cwd="terraform_config"
        )
        outputs = json.loads(result.stdout)
        bucket = outputs.get("datalake_bucket", {}).get("value")
        
        if not bucket:
            logging.error("Output \"datalake_bucket\" nao encontrado. Garanta que adicionou o output no main.tf e rodou o Terraform.")
            sys.exit(1)
            
        return bucket
    except Exception as e:
        logging.error(f"Erro ao ler output do Terraform: {e}")
        sys.exit(1)

def read_parquet_from_s3(s3_client, bucket, prefix):
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if "Contents" not in response:
        return pd.DataFrame()
        
    dfs = []
    for obj in response["Contents"]:
        if obj["Key"].endswith(".parquet"):
            obj_response = s3_client.get_object(Bucket=bucket, Key=obj["Key"])
            df = pd.read_parquet(io.BytesIO(obj_response["Body"].read()))
            dfs.append(df)
    
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)

def validate_data_lake():
    bucket_name = get_s3_bucket()
    s3 = boto3.client("s3")
    
    logging.info(f"Conectando ao bucket Data Lake: {bucket_name}")
    
    tables = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]
    dfs = {}
    
    # Criterio 2: As saidas Parquet existem e possuem registros
    for table in tables:
        logging.info(f"Lendo e validando a tabela {table} do S3...")
        df = read_parquet_from_s3(s3, bucket_name, f"output/{table}/")
        
        if df.empty:
            logging.error(f"FALHA: Tabela {table} nao encontrada ou esta vazia no S3.")
            sys.exit(1)
            
        dfs[table] = df
        logging.info(f"OK: Tabela {table} carregada com sucesso ({len(df)} registros).")
        
    fact = dfs["fact_orders"]
    
    # Criterio 3: A tabela fato referencia chaves validas das dimensoes
    logging.info("Validando integridade referencial (Chaves Estrangeiras)...")
    
    invalid_customers = fact[~fact["customer_id"].isin(dfs["dim_customers"]["customer_id"])]
    if not invalid_customers.empty:
        logging.error(f"FALHA: {len(invalid_customers)} registros na fact_orders possuem customer_id invalido.")
        sys.exit(1)
        
    invalid_products = fact[~fact["product_id"].isin(dfs["dim_products"]["product_id"])]
    if not invalid_products.empty:
        logging.error(f"FALHA: {len(invalid_products)} registros na fact_orders possuem product_id invalido.")
        sys.exit(1)
        
    logging.info("OK: Todas as chaves mapeadas na tabela fato existem nas dimensoes.")
    
    # Criterio 4: O campo sales_amount esta consistente com quantity_ordered * price_each
    logging.info("Validando regra de negocio: sales_amount = quantity_ordered * price_each...")
    
    calculated_sales = fact["quantity_ordered"] * fact["price_each"]
    
    # Coloquei uma tolerancia para evitar erros de arredondamento de floats
    diff = (fact["sales_amount"] - calculated_sales).abs()
    invalid_sales = fact[diff > 0.01]
    
    if not invalid_sales.empty:
        logging.error(f"FALHA: {len(invalid_sales)} registros na fato com 'sales_amount' inconsistente.")
        sys.exit(1)
        
    logging.info("OK: Regra de negocio validada com exito.")
    
    # Sinalizacao deterministica de sucesso
    logging.info("SUCESSO ABSOLUTO: O Data Lake S3 cumpre com todos os criterios da Task 2.")
    sys.exit(0)

if __name__ == "__main__":
    validate_data_lake()
