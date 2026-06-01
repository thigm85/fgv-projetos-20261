import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = "3306"
DB_NAME = "classicmodels"

def get_engine():
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(connection_string)

def init_watermark():
    engine = get_engine()
    
    # DDL da tabela de controle conforme especificação
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS etl_watermark (
        pipeline_name VARCHAR(64) PRIMARY KEY,
        last_processed_order_date DATE,
        last_run_at DATETIME,
        last_run_status VARCHAR(32)
    )
    """
    
    # Query para buscar a data máxima de pedido já existente no banco (baseline)
    get_max_date_sql = "SELECT MAX(orderDate) FROM orders"
    
    # Upsert: Insere o registro inicial ou atualiza se a linha de base mudou
    upsert_watermark_sql = """
    INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
    VALUES ('classicmodels_sales', :max_date, NULL, 'NEVER_RUN')
    ON DUPLICATE KEY UPDATE 
        last_processed_order_date = VALUES(last_processed_order_date),
        last_run_status = VALUES(last_run_status)
    """
    
    try:
        with engine.begin() as conn:
            print("Criando tabela etl_watermark (se não existir)...")
            conn.execute(text(create_table_sql))
            
            print("Calculando baseline a partir da tabela orders...")
            result = conn.execute(text(get_max_date_sql)).fetchone()
            max_date = result[0] if result and result[0] else None
            
            if max_date is None:
                print("Aviso: A tabela 'orders' está vazia. Não há baseline histórico.")
                return

            print(f"Data máxima encontrada na origem: {max_date}")
            
            print("Inicializando/Atualizando o watermark do pipeline 'classicmodels_sales'...")
            conn.execute(text(upsert_watermark_sql), {"max_date": max_date})
            
            print("Processo finalizado com sucesso!")
            
    except SQLAlchemyError as e:
        print(f"Erro de banco de dados: {e}")

if __name__ == "__main__":
    init_watermark()