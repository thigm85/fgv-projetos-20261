import pymysql
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import CFG, logger # Importamos o logger que configuramos lá

def upload_data():
    conn = None
    try:
        logger.info("Passo 1 - Iniciando conexão com o banco de dados...")
        
        # autocommit=False é crucial para termos controle transacional!
        conn = pymysql.connect(
            host=CFG.DB_HOST, user=CFG.DB_USER, password=CFG.DB_PASS, autocommit=False
        )
        cursor = conn.cursor()

        logger.info(f"Passo 2 - Configurando database '{CFG.DB_NAME}'")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {CFG.DB_NAME};")
        cursor.execute(f"USE {CFG.DB_NAME};")

        logger.info("Passo 3 - Lendo e executando arquivo SQL...")
        with open(CFG.SQL_PATH, 'r', encoding='utf-8') as f:
            full_sql = f.read()
            queries = full_sql.split(';\n')
            
        for query in queries:
            if query.strip():
                cursor.execute(query)
        
        conn.commit()
        logger.info("Passo 4 - Dados consolidados (commit) com sucesso!")

    except Exception as e:
        if conn:
            conn.rollback() 
        logger.error(f"Falha na carga de dados. Rollback executado. Erro: {e}")
        sys.exit(1)
        
    finally:
        if conn:
            conn.close()
            logger.info("Conexão com o banco de dados encerrada.")

if __name__ == "__main__":
    upload_data()