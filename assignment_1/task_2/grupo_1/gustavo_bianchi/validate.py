import boto3
import pandas as pd
import sys

BUCKET_NAME = "classicmodels-lake-50eb0a4d" # Alterar aqui co mo nome gerado
JOB_NAME = "classicmodels-star-schema-job"
REGION = 'us-east-1'

def validate_etl():
    print("== Iniciando validação do  ETL ==\n")
    failed_tests = 0

    # Inicializa clientes AWS
    glue = boto3.client('glue', region_name=REGION)
    s3 = boto3.client('s3', region_name=REGION)

    # Validação do Job
    print("Teste 1: Status do AWS Glue Job...")
    try:
        # Pega a última execução do job
        runs = glue.get_job_runs(JobName=JOB_NAME, MaxResults=1)
        if not runs['JobRuns']:
            print("[FAIL] Nenhuma execução encontrada para este Job.")
            sys.exit(1)
            
        last_run_status = runs['JobRuns'][0]['JobRunState']
        if last_run_status == 'SUCCEEDED':
            print(f"[PASS] Job finalizou com status {last_run_status}.")
        else:
            print(f"[FAIL] Job não teve sucesso. Status atual: {last_run_status}")
            failed_tests += 1
    except Exception as e:
        print(f"[FAIL] Erro ao consultar o Glue: {e}")
        failed_tests += 1

    # ==========================================
    # 2. Validação de Arquivos no S3
    # ==========================================
    print("\nTeste 2: Existência das saídas Parquet no S3...")
    tabelas_esperadas = ['fact_orders', 'dim_customers', 'dim_products', 'dim_dates', 'dim_countries']
    
    for tabela in tabelas_esperadas:
        # Verifica se existe algum objeto com o prefixo da pasta da tabela
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f"{tabela}/")
        if 'Contents' in response and len(response['Contents']) > 0:
            # Garante que tem arquivos parquet lá dentro, e não apenas uma pasta vazia
            has_parquet = any(obj['Key'].endswith('.parquet') for obj in response['Contents'])
            if has_parquet:
                print(f"[PASS] {tabela} existe em formato Parquet.")
            else:
                print(f"[FAIL] Pasta {tabela} existe, mas não contém arquivos .parquet.")
                failed_tests += 1
        else:
            print(f"[FAIL] Pasta/Tabela {tabela} não encontrada no S3.")
            failed_tests += 1

    # Se faltar arquivo, aborta o script antes de tentar usar o Pandas
    if failed_tests > 0:
        print("\n[ABORTANDO] Corrija os erros de infra/arquivos antes de validar os dados.")
        sys.exit(1)

    # Validando dados
    print("\nBaixando dados do S3...")
    try:
        # O s3fs permite que o pandas leia direto da nuvem
        df_fact = pd.read_parquet(f"s3://{BUCKET_NAME}/fact_orders/")
        df_dim_cust = pd.read_parquet(f"s3://{BUCKET_NAME}/dim_customers/")
        df_dim_prod = pd.read_parquet(f"s3://{BUCKET_NAME}/dim_products/")

        print("\nTeste 3: Registros na Tabela Fato e Chaves Válidas...")
        
        # Tem registros?
        if len(df_fact) > 0:
            print(f"[PASS] fact_orders contém {len(df_fact)} registros.")
        else:
            print("[FAIL] fact_orders está vazia.")
            failed_tests += 1

        # Integridade Referencial (Chaves existem nas dimensões?)
        clientes_invalidos = df_fact[~df_fact['customer_id'].isin(df_dim_cust['customer_id'])]
        produtos_invalidos = df_fact[~df_fact['product_id'].isin(df_dim_prod['product_id'])]

        if len(clientes_invalidos) == 0:
            print("[PASS] Todas as foreign keys de 'customer_id' são válidas.")
        else:
            print(f"[FAIL] {len(clientes_invalidos)} registros na fato apontam para clientes inexistentes.")
            failed_tests += 1

        if len(produtos_invalidos) == 0:
            print("[PASS] Todas as foreign keys de 'product_id' são válidas.")
        else:
            print(f"[FAIL] {len(produtos_invalidos)} registros na fato apontam para produtos inexistentes.")
            failed_tests += 1

        print("\nTestando 4: Regra de Negócio (sales_amount = quantity_ordered * price_each)...")
        
        math_check = abs(df_fact['sales_amount'] - (df_fact['quantity_ordered'] * df_fact['price_each'])) < 0.01
        erros_matematicos = (~math_check).sum()

        if erros_matematicos == 0:
            print("[PASS] O campo 'sales_amount' está 100% consistente com a regra.")
        else:
            print(f"[FAIL] {erros_matematicos} registros com falha na matemática do sales_amount.")
            failed_tests += 1

    except Exception as e:
        print(f"[FAIL] Erro crítico ao processar dados via Pandas: {e}")
        sys.exit(1)

if __name__ == "__main__":
    validate_etl()