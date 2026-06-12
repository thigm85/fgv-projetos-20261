import os
import pymysql
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Watermark Init] %(message)s', datefmt='%H:%M:%S')

# Para conseguir reaproveitar o endpoint gerado na task 1 do ass. 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENDPOINT_PATH = os.path.abspath(os.path.join(BASE_DIR, "../../../../assignment_1/task_1/grupo_1/gustavo_bianchi/rds_endpoint.txt"))

def get_rds_endpoint():
    if not os.path.exists(ENDPOINT_PATH):
        logging.error(f"Arquivo de endpoint não encontrado em: {ENDPOINT_PATH}")
        raise FileNotFoundError("Rode o terraform de criação do RDS.")
    with open(ENDPOINT_PATH, "r") as f:
        return f.read().strip()

def initialize_metadata_table():
    endpoint = get_rds_endpoint()
    db_user = "admin"
    db_password = os.environ.get("TF_VAR_db_password") # A variável deve ser definida como feito na task 1 do ass. 1
    db_name = "classicmodels"

    if not db_password:
        logging.error("Variável de ambiente 'TF_VAR_db_password' não configurada.")
        return

    # Estabelece conexão com o banco RDS MySQL
    connection = pymysql.connect(
        host=endpoint,
        user=db_user,
        password=db_password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )

    try:
        with connection.cursor() as cursor:
            # Cria a tabela de watermark se ela não existir
            logging.info("Garantindo a existência da tabela etl_watermark...")
            create_table_query = """
            CREATE TABLE IF NOT EXISTS etl_watermark (
                pipeline_name VARCHAR(64) PRIMARY KEY,
                last_processed_order_date DATE NOT NULL,
                last_run_at DATETIME NOT NULL,
                last_run_status VARCHAR(32) NOT NULL
            );
            """
            cursor.execute(create_table_query)

            # Verifica se já existe um registro de pipeline
            check_query = "SELECT pipeline_name FROM etl_watermark WHERE pipeline_name = %s;"
            cursor.execute(check_query, ('classicmodels_sales',))
            result = cursor.fetchone()

            if not result:
                logging.info("Registro inicial ausente. Calculando High-Watermark histórica...")
                
                # Busca o MAX(orderDate) atual do banco 
                max_date_query = "SELECT MAX(orderDate) as max_date FROM orders;"
                cursor.execute(max_date_query)
                max_date_result = cursor.fetchone()
                
                initial_watermark = max_date_result['max_date']

                if not initial_watermark:
                    logging.warning("Nenhum pedido encontrado na tabela 'orders'. Inicializando com data padrão.")
                    initial_watermark = "2000-01-01"

                # Insere o registro de controle inicial
                insert_query = """
                INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
                VALUES (%s, %s, UTC_TIMESTAMP(), %s);
                """
                cursor.execute(insert_query, ('classicmodels_sales', initial_watermark, 'NEVER_RUN'))
                logging.info(f"Sucesso! Watermark configurada para a data histórica: {initial_watermark}")
            else:
                logging.info("A tabela 'etl_watermark' já possui uma configuração ativa. Nenhuma alteração realizada.")
        
        connection.commit()

    except Exception as e:
        logging.error(f"Falha na inicialização dos metadados: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    initialize_metadata_table()