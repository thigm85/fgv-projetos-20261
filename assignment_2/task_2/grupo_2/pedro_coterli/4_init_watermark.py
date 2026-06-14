import os
import pymysql
from datetime import datetime

def get_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASS', ''),
        database=os.environ.get('DB_NAME', 'classicmodels'),
        cursorclass=pymysql.cursors.DictCursor
    )

def init_watermark():
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            # Cria a tabela se não existir
            create_table_query = """
            CREATE TABLE IF NOT EXISTS etl_watermark (
                pipeline_name VARCHAR(64) PRIMARY KEY,
                last_processed_order_date DATE,
                last_run_at DATETIME,
                last_run_status VARCHAR(32)
            );
            """
            cursor.execute(create_table_query)

            # Insere o registro inicial se ausente
            insert_initial_query = """
            INSERT IGNORE INTO etl_watermark (pipeline_name, last_run_status)
            VALUES ('classicmodels_sales', 'NEVER_RUN');
            """
            cursor.execute(insert_initial_query)

            # Descobre a data máxima atual em orders
            cursor.execute("SELECT MAX(orderDate) as max_date FROM orders;")
            result = cursor.fetchone()
            max_date = result['max_date'] if result['max_date'] else datetime.today().date()

            # Atualiza o watermark inicial
            update_watermark_query = """
            UPDATE etl_watermark 
            SET last_processed_order_date = %s 
            WHERE pipeline_name = 'classicmodels_sales';
            """
            cursor.execute(update_watermark_query, (max_date,))
            
            connection.commit()
            print(f"[init_watermark] Watermark inicializado com sucesso. last_processed_order_date: {max_date}")
    finally:
        connection.close()

if __name__ == "__main__":
    init_watermark()