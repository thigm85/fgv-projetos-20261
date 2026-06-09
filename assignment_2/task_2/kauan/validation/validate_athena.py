import boto3
import time
import pandas as pd
from dotenv import load_dotenv
import os

# Carrega variáveis
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, "rds_connection.env")
if not os.path.isfile(ENV_PATH):
    ENV_PATH = os.path.join(os.path.dirname(BASE_DIR), "rds_connection.env")
load_dotenv(dotenv_path=ENV_PATH)

def info(msg): print(f"[INFO] {msg}")
def error(msg): print(f"[ERRO] {msg}"); raise SystemExit(1)

def main():
    athena = boto3.client("athena")
    glue = boto3.client("glue")

    database = os.getenv("GLUE_DATABASE_NAME", "classicmodels_gold")
    workgroup = os.getenv("ATHENA_WORKGROUP_NAME", "classicmodels_workgroup")
    tables = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]

    info(f"Verificando tabelas no banco de dados Glue: {database}...")

    try:
        for table in tables:
            glue.get_table(DatabaseName=database, Name=table)
            info(f"Tabela '{table}' encontrada.")
    except Exception as e:
        error(f"Erro ao buscar tabelas: {e}")

    def run_query(query_str, desc):
        info(f"Executando no Athena: {desc}...")
        try:
            response = athena.start_query_execution(
                QueryString=query_str,
                QueryExecutionContext={'Database': database},
                WorkGroup=workgroup
            )
            query_execution_id = response['QueryExecutionId']
            while True:
                status = athena.get_query_execution(QueryExecutionId=query_execution_id)['QueryExecution']['Status']['State']
                if status in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                    break
                time.sleep(2)
                
            if status == 'SUCCEEDED':
                results = athena.get_query_results(QueryExecutionId=query_execution_id)
                rows = results['ResultSet']['Rows']
                info(f"Consulta '{desc}' bem-sucedida! Resultados:")
                for i, r in enumerate(rows):
                    if i < 6:
                        row_vals = [col.get('VarCharValue', 'NULL') for col in r['Data']]
                        print(f"  {row_vals}")
            else:
                error(f"Consulta '{desc}' falhou com status: {status}")
        except Exception as e:
            error(f"Erro ao executar '{desc}' no Athena: {e}")

    # Query 1: Contagem total
    run_query(f"SELECT count(*) as total_rows FROM fact_orders", "Contagem total em fact_orders")

    # Query 2: Filtrado por partição (Task 2)
    run_query(
        "SELECT order_year, order_month, count(*) as count FROM fact_orders GROUP BY order_year, order_month ORDER BY order_year DESC, order_month DESC LIMIT 5",
        "Contagem por partição (order_year, order_month)"
    )

    print("\n" + "="*50)
    print(" VALIDAÇÃO DO ATHENA CONCLUÍDA! ")
    print(" Agora você pode abrir o notebook dashboard.ipynb ")
    print("="*50)

if __name__ == "__main__":
    main()
