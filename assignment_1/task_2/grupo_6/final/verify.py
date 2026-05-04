import mysql.connector
from mysql.connector import errorcode
import os
import json
import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_db_endpoint():
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            capture_output=True, text=True, check=True, cwd="terraform_config"
        )
        outputs = json.loads(result.stdout)
        endpoint = outputs.get("db_endpoint", {}).get("value")
        if not endpoint:
            logging.error("Output 'db_endpoint' nao encontrado.")
            sys.exit(1)
        return endpoint.split(":")[0]
    except Exception as e:
        logging.error(f"Erro ao ler output do Terraform: {e}")
        sys.exit(1)

config = {
    "user": os.environ.get("DB_USER", "admin_user"),
    "password": os.environ.get("DB_PASSWORD"),
    "host": get_db_endpoint(),
    "database": "classicmodels",
    "ssl_ca": "./global-bundle.pem",
    "ssl_verify_cert": True,
    "use_pure": True
}



thresholds = {
    "customers": 122,
    "products": 110,
    "productlines": 7, 
    "orders": 326,
    "orderdetails": 2996,
    "payments": 273,
    "employees": 23,
    "offices": 7
}
expected_tables = ["customers", "products", "productlines", "orders", "orderdetails", "payments", "employees", "offices"]

def validate():
    status_final = True
    try:
        logging.info("Iniciando validacao de integridade...")
        with mysql.connector.connect(**config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                existing_tables = [table[0] for table in cursor.fetchall()]
                
                for table in expected_tables:
                    if table not in existing_tables:
                        logging.error(f"CRITICO: Tabela '{table}' ausente!")
                        status_final = False
                        continue
                    
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    
                    min_val = thresholds.get(table, 1) # Pelo menos 1 se nao estiver no dict
                    if count >= min_val:
                        logging.info(f"Tabela '{table}' validada ({count} registros).")
                    else:
                        logging.error(f"FALHA: Tabela '{table}' possui apenas {count} registros (Minimo esperado: {min_val}).")
                        status_final = False

        if status_final:
            logging.info("Validacao concluida com SUCESSO.")
            sys.exit(0)
        else:
            logging.error("Validacao concluida com ERROS.")
            sys.exit(1) 

    except mysql.connector.Error as err:
        logging.error(f"Erro de conexao ou SQL: {err}")
        sys.exit(1)

if __name__ == "__main__":
    validate()
