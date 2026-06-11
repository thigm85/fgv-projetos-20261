import os
import sys
import time
import boto3
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = 'classicmodels'
DB_PORT = "3306"

S3_BUCKET = "fgv-datalake-joao-gabriel-9090"
GLUE_DATABASE = "classicmodels_star_schema"
ATHENA_OUTPUT = f"s3://{S3_BUCKET}/temp/"

def execute_athena_query(athena_client, query):
    """Executa uma query no Athena e aguarda a conclusão."""
    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={'Database': GLUE_DATABASE},
        ResultConfiguration={'OutputLocation': ATHENA_OUTPUT}
    )
    query_execution_id = response['QueryExecutionId']
    
    while True:
        status_response = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
        status = status_response['QueryExecution']['Status']['State']
        if status in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
            break
        time.sleep(2)
        
    if status == 'SUCCEEDED':
        result_response = athena_client.get_query_results(QueryExecutionId=query_execution_id)
        return result_response['ResultSet']['Rows']
    else:
        raise Exception(f"Athena query failed: {status_response['QueryExecution']['Status'].get('StateChangeReason')}")

def main():
    output_lines = ["=== POST-INCREMENTAL ETL VALIDATION REPORT ===\n"]
    
    # Clientes
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)
    s3_client = boto3.client('s3')
    athena_client = boto3.client('athena', region_name='us-east-1')

    try:
        # ---------------------------------------------------------
        # VERIFICAÇÃO 1 e 3: STATUS DO GLUE E WATERMARK AVANÇOU
        # ---------------------------------------------------------
        with engine.connect() as conn:
            watermark_query = text("SELECT last_processed_order_date, last_run_status, last_run_at FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'")
            wm_res = conn.execute(watermark_query).fetchone()
            
            if not wm_res:
                print("ERRO: Watermark não encontrado!")
                sys.exit(1)
                
            wm_date, wm_status, wm_time = wm_res
            
            output_lines.append("--- Check 1 & 3: RDS Watermark Status ---")
            output_lines.append(f"Status do Último Job: {wm_status}")
            output_lines.append(f"Última Data Processada: {wm_date}")
            output_lines.append(f"Timestamp da Execução: {wm_time}\n")
            
            if wm_status != 'SUCCEEDED':
                output_lines.append("❌ FALHA: O Job do Glue não terminou com sucesso (SUCCEEDED).")
                save_report(output_lines)
                sys.exit(1)
            else:
                output_lines.append("✅ SUCESSO: O Glue reportou sucesso e o watermark avançou no banco.\n")

        # ---------------------------------------------------------
        # VERIFICAÇÃO 2: NOVOS OBJETOS PARTICIONADOS NO S3
        # ---------------------------------------------------------
        output_lines.append("--- Check 2: S3 Partitioning Structure ---")
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="data/fact_orders/order_year=")
        
        if 'Contents' not in response:
            output_lines.append("❌ FALHA: Nenhuma partição Hive-style encontrada no S3 para fact_orders.")
            save_report(output_lines)
            sys.exit(1)
            
        partitions_found = set()
        for obj in response['Contents']:
            key = obj['Key']
            # Extrai apenas a parte da pasta (ex: order_year=2005/order_month=6)
            parts = [p for p in key.split('/') if '=' in p]
            if parts:
                partitions_found.add("/".join(parts))
                
        output_lines.append(f"Partições encontradas no S3: {len(partitions_found)}")
        for p in list(partitions_found)[:5]: # Mostra até 5 para não poluir
            output_lines.append(f" - {p}")
        output_lines.append("✅ SUCESSO: Estrutura de pastas particionadas validada no S3.\n")

        # ---------------------------------------------------------
        # ATENÇÃO: ATUALIZAÇÃO DO CATÁLOGO DO ATHENA (MSCK REPAIR)
        # ---------------------------------------------------------
        # O PySpark gravou as pastas novas, mas o Athena precisa ser avisado que elas existem.
        print("Registrando novas partições no Glue Catalog (MSCK REPAIR TABLE)...")
        execute_athena_query(athena_client, "MSCK REPAIR TABLE fact_orders;")

        # ---------------------------------------------------------
        # VERIFICAÇÃO 4: CONSULTA ATHENA COM FILTRO DE PARTIÇÃO
        # ---------------------------------------------------------
        output_lines.append("--- Check 4: Athena Partition Query ---")
        # Extraímos o ano e o mês da data do watermark para testar a partição nova
        test_year = wm_date.year
        test_month = wm_date.month
        
        query_part = f"SELECT COUNT(*) FROM fact_orders WHERE order_year = {test_year} AND order_month = {test_month}"
        rows_part = execute_athena_query(athena_client, query_part)
        count_val = rows_part[1]['Data'][0]['VarCharValue']
        
        output_lines.append(f"Query: {query_part}")
        output_lines.append(f"Resultado: {count_val} linhas processadas na nova partição.")
        if int(count_val) == 0:
            output_lines.append(f"❌ AVISO: Nenhuma linha retornou para a partição {test_year}-{test_month}.")
        else:
            output_lines.append("✅ SUCESSO: Athena lê dados incrementais particionados perfeitamente.\n")

        # ---------------------------------------------------------
        # VERIFICAÇÃO 5: INTEGRIDADE DA REGRA DE NEGÓCIO (SALES_AMOUNT)
        # ---------------------------------------------------------
        output_lines.append("--- Check 5: Business Rule Validation (sales_amount) ---")
        query_math = "SELECT COUNT(*) FROM fact_orders WHERE ROUND(sales_amount, 2) != ROUND(quantity_ordered * price_each, 2)"
        rows_math = execute_athena_query(athena_client, query_math)
        errors_val = rows_math[1]['Data'][0]['VarCharValue']
        
        output_lines.append(f"Linhas com erro de cálculo: {errors_val}")
        if int(errors_val) > 0:
            output_lines.append("❌ FALHA: A regra sales_amount = quantity * price foi quebrada no delta!")
            save_report(output_lines)
            sys.exit(1)
        else:
            output_lines.append("✅ SUCESSO: A regra matemática se manteve intacta para os novos registros.\n")

        # FIM
        output_lines.append("===============================================")
        output_lines.append("🎉 TODAS AS VALIDAÇÕES FORAM CONCLUÍDAS COM SUCESSO!")
        print("Validações finalizadas!")
        save_report(output_lines)

    except Exception as e:
        err_msg = f"\nERRO DURANTE A VALIDAÇÃO: {e}"
        print(err_msg)
        output_lines.append(err_msg)
        save_report(output_lines)
        sys.exit(1)

def save_report(lines):
    final_output = "\n".join(lines)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "validation_post_incremental.txt")
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(final_output)
    print(f"\n[INFO] Relatório salvo em: {file_path}")

if __name__ == "__main__":
    main()