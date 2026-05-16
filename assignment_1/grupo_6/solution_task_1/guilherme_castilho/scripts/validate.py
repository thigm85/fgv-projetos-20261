import mysql.connector

# Utilize as mesmas configurações do script de carga
DB_CONFIG = {
    "host": "terraform-20260407235920750500000001.cejyiy0y8cii.us-east-1.rds.amazonaws.com",
    "user": "admin",
    "password": "password",
    "database": "classicmodels",
    "port": 3306,
    'use_pure': True
}

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
            return

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
        print("Validação concluída: O sistema de origem está pronto!")

    except mysql.connector.Error as err:
        print(f"Erro durante a validação: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    validate_database()