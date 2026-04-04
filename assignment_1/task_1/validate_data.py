import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST") # O endpoint do RDS
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

def validate():
    try:
        print(f"Validando dados no banco {DB_NAME} em {DB_HOST}...")
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()
        
        tables = [
            "customers", "products", "productlines", 
            "orders", "orderdetails", "payments", 
            "employees", "offices"
        ]
        
        print(f"{'Tabela':<20} | {'Linhas':<10}")
        print("-" * 35)
        
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"{table:<20} | {count:<10}")
            
        cursor.close()
        conn.close()
        print("\nValidação concluída com sucesso!")
        
    except mysql.connector.Error as err:
        print(f"Erro na validação: {err}")

if __name__ == "__main__":
    if not DB_HOST:
        print("Erro: DB_HOST não definido.")
    else:
        validate()
