import mysql.connector
from mysql.connector import errorcode

import os
import sys
import subprocess
import json
import logging
import time


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_db_endpoint():
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            capture_output=True,
            text=True,
            check=True,
            cwd="terraform_config"
        )
        outputs = json.loads(result.stdout)
        endpoint = outputs.get("db_endpoint", {}).get("value")
        if not endpoint:
            logging.error("Output 'db_endpoint' nao encontrado no Terraform.")
            sys.exit(1)
        return endpoint.split(":")[0]
    except Exception as e:
        logging.error(f"Erro ao ler output do Terraform: {e}")
        sys.exit(1)

def sql_secure_split(sql_script):
    statements = []
    current_statement = []
    in_string = False
    string_char = ""
    escape_next = False
    
    for char in sql_script:
        if escape_next:
            escape_next = False
        elif char == "\\":
            escape_next = True
        elif (char == "\'" or char == "\"") and not in_string:
            in_string = True
            string_char = char
        elif char == string_char and in_string:
            in_string = False
            
        if char == ";" and not in_string:
            statements.append("".join(current_statement))
            current_statement = []
        else:
            current_statement.append(char)
            
    if "".join(current_statement).strip():
        statements.append("".join(current_statement))
    return statements

config = {
    "user": os.environ.get("DB_USER", "admin_user"),
    "password": os.environ.get("DB_PASSWORD"),
    "host": get_db_endpoint(),
    "database": "classicmodels",
    "ssl_ca": "./global-bundle.pem",
    "ssl_verify_cert": True,
    "use_pure": True,
    "autocommit": False 
}

if not config["password"]:
    logging.error("Variavel de ambiente DB_PASSWORD nao definida.")
    sys.exit(1)

# Implementação de Retries
max_retries = 3
retry_delay = 5
conn = None

for attempt in range(1, max_retries + 1):
    try:
        logging.info(f"Tentativa {attempt}/{max_retries}: Conectando ao banco de dados...")
        conn = mysql.connector.connect(**config)
        
        if conn.is_connected():
            cursor = conn.cursor()
            
            with open("data/mysqlsampledatabase.sql", "r", encoding="utf-8") as f:
                sql_file = f.read()
            
            logging.info("Executando carga de dados transacional...")
            
            instrucoes = sql_secure_split(sql_file)
            for instrucao in instrucoes:
                if instrucao.strip():
                    cursor.execute(instrucao)
            
            conn.commit() 
            logging.info("Carga concluida com sucesso!")
            cursor.close()
            conn.close()
            sys.exit(0)

    except mysql.connector.Error as err:
        if conn and conn.is_connected():
            conn.rollback()
            logging.warning("Erro detectado. Realizando rollback da transacao.")
        
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error("Usuario ou senha incorretos.")
            break 
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logging.error("Banco de dados nao existe.")
            break
        else:
            logging.error(f"Erro de banco de dados: {err}")
            
        if attempt < max_retries:
            logging.info(f"Aguardando {retry_delay}s para nova tentativa...")
            time.sleep(retry_delay)
        else:
            logging.error("Numero maximo de tentativas atingido.")
            sys.exit(1)

    except Exception as e:
        logging.error(f"Erro inesperado: {e}")
        sys.exit(1)
