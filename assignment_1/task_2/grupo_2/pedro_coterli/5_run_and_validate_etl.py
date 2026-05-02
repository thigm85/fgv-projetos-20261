import time
import boto3
import awswrangler as wr
import pandas as pd

# Configurações
JOB_NAME = "classicmodels_star_schema_etl"
REGION = "us-east-1"
BUCKET_NAME = "classicmodels-datalake-pedro-coterli"
BASE_PATH = f"s3://{BUCKET_NAME}/output"

def run_and_wait_glue_job():
    print(f"Iniciando o Job do Glue: '{JOB_NAME}'...")

    # Criando o cliente do Glue
    glue_client = boto3.client("glue", region_name = REGION)

    # Disparando o Job
    response = glue_client.start_job_run(JobName = JOB_NAME)
    job_run_id = response["JobRunId"]

    print(f"Job disparado com sucesso. (Run ID: {job_run_id})")
    print("Aguardando a execução...")

    # Loop de repetição para checar o status
    while True:
        status_response = glue_client.get_job_run(JobName = JOB_NAME, RunId = job_run_id)
        status = status_response["JobRun"]["JobRunState"]

        print(f" -> Status atual: {status}...")

        if status == "SUCCEEDED":
            print("\nO Job finalizou com sucesso. Avançando para a validação...\n")
            break
        elif status in ["FAILED", "STOPPED", "TIMEOUT"]:
            error_msg = status_response["JobRun"].get("ErrorMessage", "Erro desconhecido.")
            print(f"\nO Job falhou com status {status}. Mensagem de erro: {error_msg}")
            # Interrompe o script se der erro
            raise SystemExit("Pipeline abortado devido a erro no Glue.")
        
        # Espera 20 segundos antes de perguntar para a AWS de novo
        time.sleep(20)

def validate_etl():
    print("-"*50)
    print("Iniciando a validação final do ETL...")
    print("-"*50)

    # Verificando se as saídas Parquet de fact_orders e das dimensões existem
    print("--- Verificando a existência dos arquivos Parquet no S3 ---")

    expected_tables = ["dim_customers", "dim_products", "dim_dates", "dim_countries", "fact_orders"]

    for table in expected_tables:
        path = f"{BASE_PATH}/{table}/"
        files = wr.s3.list_objects(path)

        if files:
            print(f" -> Encontrado: '{table}' ({len(files)} arquivo(s))")
        else:
            print(f" -> Faltando: '{table}'")

    print("\nLendo os dados para DataFrames do Pandas...")

    df_fact = wr.s3.read_parquet(f"{BASE_PATH}/fact_orders/")
    df_dim_prod = wr.s3.read_parquet(f"{BASE_PATH}/dim_products/")
    df_dim_cust = wr.s3.read_parquet(f"{BASE_PATH}/dim_customers/")

    # Verificando se a tabela fato contém registros
    print("\n--- Verificando registros na tabela fato ---")

    if not df_fact.empty:
        print(f" -> fact_orders contém dados (total: {len(df_fact)} linhas).")
    else:
        print(" -> fact_orders está vazia!")

    # Verificando as referências a chaves válidas das dimensões
    print("\n--- Validando integridade referencial ---")

    # Transformando as colunas de ID em sets para cruzar os dados
    products_fact = set(df_fact["product_id"])
    products_dim = set(df_dim_prod["product_id"])

    invalid_products = products_fact - products_dim

    if len(invalid_products) == 0:
        print(" -> Referência válida: Todos os product_id da fato existem na dim_products.")
    else:
        print(f" -> Referência inválida: {len(invalid_products)} product_id na fato não existem na dimensão.")

    clients_fact = set(df_fact["customer_id"])
    clients_dim = set(df_dim_cust["customer_id"])

    invalid_clients = clients_fact - clients_dim

    if len(invalid_clients) == 0:
        print(" -> Referência válida: Todos os customer_id da fato existem na dim_customers.")
    else:
        print(f" -> Referência inválida: {len(invalid_clients)} customer_id na fato não existem na dimensão.")

    # Verificando a consistência do sales_amount
    print("\n--- Validando regra de negócio ---")

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
        print(" -> Cálculo correto: 'sales_amount' é igual a 'quantity_ordered * price_each' em todas as linhas.")
    else:
        print(f" -> Inconsistência: Encontradas {len(divergences)} linhas com cálculo incorreto.")

    print("\nVALIDAÇÃO DO PIPELINE ETL CONCLUÍDA.")

if __name__ == "__main__":
    # Executa e aguarda
    run_and_wait_glue_job()
    # Depois que termina, roda a validação
    validate_etl()