import os
import sys
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "classicmodels"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "use_pure": True
}

EXPECTED_TABLES = [
    "customers", "employees", "offices", "orderdetails", 
    "orders", "payments", "productlines", "products"
]

def validate_database():
    print("Iniciando validação do banco de dados no RDS...\n")
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 1. Verifica quais tabelas foram criadas
        cursor.execute("SHOW TABLES")
        tables = [table[0] for table in cursor.fetchall()]
        
        if not tables:
            print("Nenhuma tabela encontrada. Verifique o script de carga.")
            sys.exit(1)

        print(f"Foram encontradas {len(tables)} tabelas. Verificando o volume de dados:\n")
        print("-" * 40)
        print(f"{'NOME DA TABELA':<20} | {'Nº DE REGISTROS':>15}")
        print("-" * 40)

        # 2. Conta as linhas de cada tabela para validar o insert
        total_records = 0
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            total_records += count
            print(f"{table:<20} | {count:>15}")

        print("-" * 40)
        print(f"{'TOTAL GERAL':<20} | {total_records:>15}\n")

        missing_tables = [t for t in EXPECTED_TABLES if t not in tables]
        if missing_tables:
            print(f"-> FALHA: Estão faltando as seguintes tabelas: {missing_tables}")
            sys.exit(1)

        if total_records == 0:
            print("-> FALHA: Nenhuma linha foi inserida no banco.")
            sys.exit(1)

        print("Validação concluída: O sistema de origem está pronto!")
        sys.exit(0)

    except mysql.connector.Error as err:
        print(f"Erro durante a validação: {err}")
        sys.exit(1)
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    validate_database()