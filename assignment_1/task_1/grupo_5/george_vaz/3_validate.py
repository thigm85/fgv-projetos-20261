import mysql.connector
import os

DB_HOST = 'classicmodels-db.c2zxcfdeoqyt.us-east-1.rds.amazonaws.com'
DB_USER = os.getenv('aws_user')
DB_PASSWORD = os.getenv('aws_password')
DB_NAME = 'classicmodels'

def validate_database():
    tables_to_check = [
        'productlines', 'products', 'offices', 'employees', 
        'customers', 'payments', 'orders', 'orderdetails'
    ]

    print(f"Conectando ao banco de dados '{DB_NAME}' para validação...\n")
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = connection.cursor()

        print(f"{'TABELA':<20} | {'STATUS':<15} | {'QTD LINHAS'}")
        print("-" * 55)

        all_valid = True

        for table in tables_to_check:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                row_count = cursor.fetchone()[0]
                
                if row_count > 0:
                    status = "OK"
                else:
                    status = "VAZIA"
                    all_valid = False
                    
                print(f"{table:<20} | {status:<15} | {row_count}")
                
            except mysql.connector.Error as err:
                print(f"{table:<20} | ERRO        | {err.msg}")
                all_valid = False

        print("-" * 55)
        if all_valid:
            print("\nValidação concluída: Todas as tabelas existem e contêm dados!")
        else:
            print("\nValidação concluída com avisos ou erros. Verifique a tabela acima.")

    except Exception as e:
        print(f"Erro ao conectar ou validar o banco: {e}")
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

if __name__ == "__main__":
    validate_database()