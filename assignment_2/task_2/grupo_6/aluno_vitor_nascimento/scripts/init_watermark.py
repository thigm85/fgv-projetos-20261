import logging
import os
import sys
from datetime import datetime, timezone

import mysql.connector
from dotenv import find_dotenv, load_dotenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Search for the .env file recursively or check known locations
dotenv_path = find_dotenv()
if not dotenv_path:
    for path in [".env", "src/.env", "../src/.env", "../../src/.env"]:
        if os.path.exists(path):
            dotenv_path = path
            break

if dotenv_path:
    logger.info(f"Carregando variáveis de ambiente de: {dotenv_path}")
    load_dotenv(dotenv_path)
else:
    logger.info("Tentando carregar variáveis de ambiente padrão")
    load_dotenv()


def init_watermark():
    db_host = os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")

    if not all([db_host, db_user, db_pass, db_name]):
        logger.error("Erro: Variáveis de conexão ao banco de dados incompletas no .env")
        sys.exit(1)

    logger.info(f"Conectando ao banco {db_name} em {db_host}...")

    conn = None
    try:
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_pass,
            database=db_name,
            use_pure=True,
        )
        cursor = conn.cursor()

        # 1. Criar a tabela se não existir
        logger.info("Verificando/Criando a tabela 'etl_watermark'...")
        create_table_query = """
        CREATE TABLE IF NOT EXISTS etl_watermark (
            pipeline_name VARCHAR(64) PRIMARY KEY,
            last_processed_order_date DATE,
            last_run_at DATETIME,
            last_run_status VARCHAR(32)
        )
        """
        cursor.execute(create_table_query)
        conn.commit()

        # 2. Verificar se o registro inicial já existe
        pipeline_name = "classicmodels_sales"
        cursor.execute(
            "SELECT pipeline_name, last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
            (pipeline_name,),
        )
        row = cursor.fetchone()

        if row:
            logger.info(
                f"[OK] Registro para '{pipeline_name}' já existe. Watermark atual: {row[1]}"
            )
        else:
            # 3. Obter o MAX(orderDate) atual
            logger.info("Obtendo a data máxima atual de pedidos (MAX(orderDate))...")
            cursor.execute("SELECT MAX(orderDate) FROM orders")
            max_date = cursor.fetchone()[0]

            if not max_date:
                # Caso a tabela esteja vazia, usa a data atual do sistema como fallback
                max_date = datetime.now(timezone.utc).date()
                logger.warning(
                    f"Nenhum pedido encontrado. Usando data atual como fallback: {max_date}"
                )
            else:
                logger.info(f"Data máxima de pedido encontrada: {max_date}")

            # Inserir o registro inicial
            logger.info(
                f"Inserindo watermark inicial de '{pipeline_name}' com data {max_date}..."
            )
            insert_query = """
            INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
            VALUES (%s, %s, %s, %s)
            """
            # UTC timestamp para last_run_at
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                insert_query, (pipeline_name, max_date, now_utc, "NEVER_RUN")
            )
            conn.commit()
            logger.info("[OK] Inicialização concluída com sucesso.")

    except Exception as e:
        logger.error(f"Erro ao inicializar watermark: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    init_watermark()
