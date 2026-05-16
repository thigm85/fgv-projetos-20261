import os
import sys
import logging
import mysql.connector
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

EXPECTED_TABLES = {
    "customers": 122,
    "employees": 23,
    "offices": 7,
    "orderdetails": 2996,
    "orders": 326,
    "payments": 273,
    "productlines": 7,
    "products": 110
}

def validate():
    db_host = os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")

    logger.info(f"Iniciando validação do banco: {db_name}")
    
    success = True
    try:
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_pass,
            database=db_name,
            use_pure=True,
        )
        cursor = conn.cursor()

        # 1. Validar existência e contagem mínima
        for table, min_count in EXPECTED_TABLES.items():
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                
                if count >= min_count:
                    logger.info(f"[OK] Tabela '{table}': {count} registros (mín: {min_count})")
                else:
                    logger.error(f"[FALHA] Tabela '{table}': {count} registros (esperado ao menos {min_count})")
                    success = False
            except mysql.connector.Error:
                logger.error(f"[FALHA] Tabela '{table}' não encontrada no banco.")
                success = False

        cursor.execute("""
            SELECT COUNT(*) FROM orders o 
            LEFT JOIN orderdetails d ON o.orderNumber = d.orderNumber 
            WHERE d.orderNumber IS NULL
        """)
        orphans = cursor.fetchone()[0]
        if orphans == 0:
            logger.info("[OK] Integridade Referencial: Nenhuma ordem órfã encontrada.")
        else:
            logger.error(f"[FALHA] Integridade: {orphans} ordens sem detalhes detectadas.")
            success = False

    except Exception as e:
        logger.error(f"Erro fatal na validação: {e}")
        sys.exit(1)
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()

    if success:
        logger.info("VALIDAÇÃO CONCLUÍDA COM SUCESSO.")
        sys.exit(0)
    else:
        logger.error("VALIDAÇÃO REPROVADA.")
        sys.exit(1)

if __name__ == "__main__":
    validate()
