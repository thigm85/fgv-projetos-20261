import os
import time
import logging
import sqlparse
import mysql.connector
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

def get_env_var(name, required=True):
    val = os.getenv(name)
    if required and not val:
        raise EnvironmentError(f"Variável obrigatória ausente: {name}")
    return val

def load_data():
    logger.info("Passo 1/4 - Validando variáveis de ambiente")
    try:
        db_host = get_env_var("DB_HOST")
        db_user = get_env_var("DB_USER")
        db_pass = get_env_var("DB_PASS")
        sql_file = os.getenv("SQL_FILE", "../../data/mysqlsampledatabase.sql")
    except EnvironmentError as e:
        logger.error(e)
        return

    conn = None
    max_retries = 5
    retry_delay = 10
    
    logger.info("Passo 2/4 - Conectando ao RDS (com retries)")
    for attempt in range(1, max_retries + 1):
        try:
            conn = mysql.connector.connect(
                host=db_host,
                user=db_user,
                password=db_pass,
                use_pure=True
            )
            break
        except mysql.connector.Error as err:
            if attempt == max_retries:
                logger.error(f"Falha definitiva após {max_retries} tentativas: {err}")
                return
            logger.warning(f"Tentativa {attempt} falhou. Retentando em {retry_delay}s...")
            time.sleep(retry_delay)

    try:
        cursor = conn.cursor()
        
        logger.info(f"Passo 3/4 - Lendo arquivo SQL: {sql_file}")
        with open(sql_file, "r", encoding="utf-8") as file:
            sql_script = file.read()
        
        sql_commands = sqlparse.split(sql_script)
        
        logger.info(f"Passo 4/4 - Executando {len(sql_commands)} comandos em transação")
        
        conn.autocommit = False
        for command in sql_commands:
            clean_command = command.strip()
            if clean_command:
                cursor.execute(clean_command)
        
        conn.commit()
        logger.info("Sucesso: Carga de dados concluída!")

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Erro durante a carga: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            logger.info("Conexão fechada.")

if __name__ == "__main__":
    load_data()
