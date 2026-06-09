import os
import json
import subprocess
import boto3
import pandas as pd
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv(dotenv_path="rds_connection.env")

def info(msg):  print(f"[INFO] {msg}")
def warn(msg):  print(f"[AVISO] {msg}")
def error(msg):
    print(f"[ERRO] {msg}")
    raise SystemExit(1)
def step(num, total, msg): print(f"\n[VALIDAÇÃO {num}/{total}] {msg}")

def run_command(cmd, cwd=None) -> str:
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        return result.stdout or ""
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        error(f"Falha ao executar comando: {' '.join(cmd)}")
        raise

def main():
    total_steps = 2
    tf_dir = "terraform"

    # Captura bucket name via Terraform output
    try:
        outputs_raw = run_command(["terraform", "output", "-json"], cwd=tf_dir)
        outputs = json.loads(outputs_raw)
        bucket_name = outputs["s3_bucket_name"]["value"]
    except Exception as e:
        error(f"Não foi possível obter o nome do bucket do Terraform: {e}")

    # Passo 1: Validação de arquivos no S3
    step(1, total_steps, f"Validando arquivos Parquet no S3 (Bucket: {bucket_name})")
    s3 = boto3.client("s3")
    expected_tables = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]
    
    for table in expected_tables:
        prefix = f"gold/{table}/"
        objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        if "Contents" in objects:
            print(f"[OK] Tabela {table} encontrada no S3.")
        else:
            error(f"Tabela {table} NÃO encontrada no S3 (Caminho: {prefix})")

    # Passo 2: Validação de Conteúdo (Data Quality)
    step(2, total_steps, "Validando consistência dos dados (Critério 4.6)")
    
    # Lendo a tabela fato diretamente do S3 via pandas/s3fs
    path_fact = f"s3://{bucket_name}/gold/fact_orders/"
    try:
        df_fact = pd.read_parquet(path_fact)
    except Exception as e:
        error(f"Falha ao ler tabela fato do S3: {e}")
    
    if df_fact.empty:
        error("A tabela fact_orders está vazia.")
    
    # Validação da regra: sales_amount = quantity_ordered * price_each
    info("Checando integridade da métrica sales_amount...")
    df_fact["check_amount"] = (df_fact["quantity_ordered"] * df_fact["price_each"]).round(2)
    diffs = df_fact[df_fact["sales_amount"] != df_fact["check_amount"]]
    
    if diffs.empty:
        print("[OK] Métrica sales_amount consistente em todos os registros.")
    else:
        warn(f"Encontradas {len(diffs)} divergências no sales_amount!")
        print(diffs[["order_id", "sales_amount", "check_amount"]].head())

    print("\n" + "="*50)
    print(" VALIDAÇÃO DO ETL CONCLUÍDA COM SUCESSO! ")
    print("="*50)

if __name__ == "__main__":
    main()
