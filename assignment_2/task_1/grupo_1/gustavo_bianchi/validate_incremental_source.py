import os
import sys
import pymysql
import logging

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [Integrity Validation] %(levelname)s - %(message)s', 
    datefmt='%H:%M:%S'
)

# Para conseguir reaproveitar o endpoint gerado na task 1 do ass. 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENDPOINT_PATH = os.path.abspath(os.path.join(BASE_DIR, "../../../../assignment_1/task_1/grupo_1/gustavo_bianchi/rds_endpoint.txt"))

def get_rds_endpoint():
    if not os.path.exists(ENDPOINT_PATH):
        logging.error(f"Arquivo de endpoint não encontrado em: {ENDPOINT_PATH}")
        sys.exit(1)
    with open(ENDPOINT_PATH, "r") as f:
        return f.read().strip()

def run_validation():
    endpoint = get_rds_endpoint()
    db_user = "admin"
    db_password = os.environ.get("TF_VAR_db_password")
    db_name = "classicmodels"

    if not db_password:
        logging.error("Variável de ambiente 'TF_VAR_db_password' não foi configurada.")
        sys.exit(1)

    connection = pymysql.connect(
        host=endpoint,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )

    validation_passed = True

    try:
        with connection.cursor() as cursor:
            logging.info("Checagem 1 & 2: Validando tabela etl_watermark e registro de controle...")
            try:
                wm_query = """
                SELECT last_processed_order_date 
                FROM etl_watermark 
                WHERE pipeline_name = 'classicmodels_sales';
                """
                cursor.execute(wm_query)
                wm_record = cursor.fetchone()
            except pymysql.err.OperationalError as e:
                if e.args[0] == 1146: # Código de erro para tabela não existente
                    logging.error("FALHA: A tabela 'etl_watermark' não existe no banco de dados.")
                    sys.exit(1)
                raise e

            if not wm_record:
                logging.error("FALHA: Registro 'classicmodels_sales' não foi encontrado em etl_watermark.")
                validation_passed = False
            elif wm_record['last_processed_order_date'] is None:
                logging.error("FALHA: O campo 'last_processed_order_date' está nulo (NULL).")
                validation_passed = False
            else:
                last_processed_date = wm_record['last_processed_order_date']
                logging.info(f"OK: Watermark localizada. Última data processada histórica: {last_processed_date}")

            # Se as primeiras checagens falharem, interrompe a validação
            if not validation_passed:
                sys.exit(1)

            logging.info("Checagem 3: Verificando a existência de novos pedidos pós-watermark...")
            max_date_query = "SELECT MAX(orderDate) as max_date FROM orders;"
            cursor.execute(max_date_query)
            max_date_record = cursor.fetchone()
            max_order_date = max_date_record['max_date']

            if not max_order_date:
                logging.error("FALHA: A tabela 'orders' está vazia. Não foi possível calcular o MAX(orderDate).")
                validation_passed = False
            elif max_order_date <= last_processed_date:
                logging.error(
                    f"FALHA: MAX(orders.orderDate) [{max_order_date}] não é maior que a "
                    f"watermark [{last_processed_date}]. Execute o script de simulação primeiro."
                )
                validation_passed = False
            else:
                logging.info(f"OK: Dados novos detectados. Data máxima atual na origem: {max_order_date}")

            logging.info("Checagem 4: Validando integridade das linhas de itens (orderdetails) dos novos pedidos...")
            integrity_query = """
            SELECT COUNT(o.orderNumber) as orphaned_count
            FROM orders o
            LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
            WHERE o.orderDate > %s AND od.orderNumber IS NULL;
            """
            cursor.execute(integrity_query, (last_processed_date,))
            integrity_record = cursor.fetchone()
            orphaned_count = integrity_record['orphaned_count']

            if orphaned_count > 0:
                logging.error(f"FALHA: Encontrados {orphaned_count} pedidos novos sem registros associados em 'orderdetails'.")
                validation_passed = False
            else:
                logging.info("OK: Todos os novos pedidos simulados possuem itens válidos cadastrados em orderdetails.")

        if validation_passed:
            logging.info("SUCESSO: Todas as checagens de validação incremental passaram com êxito. Origem pronta para o ETL.")
            sys.exit(0)
        else:
            logging.error("FALHA: O sistema de origem falhou em uma ou mais validações de integridade.")
            sys.exit(1)

    except Exception as e:
        logging.error(f"Erro inesperado durante o processo de validação: {e}")
        sys.exit(1)
    finally:
        connection.close()

if __name__ == "__main__":
    run_validation()