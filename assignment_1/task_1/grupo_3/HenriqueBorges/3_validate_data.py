import json
import pymysql
from dotenv import load_dotenv
import os
from pathlib import Path

# Carregar .env
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Ler credenciais do .env
password = os.getenv('RDS_ADMIN_PASSWORD')

# Ler informações do RDS do rds_info.json
rds_info_path = Path(__file__).parent / 'rds_info.json'

try:
    with open(rds_info_path, 'r') as f:
        rds_info = json.load(f)

    host = rds_info['endpoint']
    user = rds_info['admin_user']
    port = rds_info['port']
    database = rds_info['database']

except FileNotFoundError:
    print(" Arquivo rds_info.json não encontrado!")
    print("   Execute primeiro o script 1_provision_rds.py")
    exit(1)

def validate_data():
    """
    Valida se os dados foram carregados corretamente no RDS
    """
    try:
        print(" Conectando ao RDS para validação...")

        # Conectar ao RDS
        connection = pymysql.connect(
            host=host,
            user=user,
            password=password,
            port=port,
            database=database
        )

        cursor = connection.cursor()
        print(" Conectado ao RDS com sucesso!\n")

        # 1. Verificar se banco existe
        print("=" * 60)
        print("1️  VALIDANDO BANCO DE DADOS")
        print("=" * 60)

        cursor.execute("SELECT DATABASE();")
        db_name = cursor.fetchone()[0]
        print(f" Banco de dados ativo: {db_name}\n")

        # 2. Listar todas as tabelas
        print("=" * 60)
        print("2️  LISTANDO TABELAS")
        print("=" * 60)

        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
        """, (database,))

        tables = cursor.fetchall()
        table_names = [table[0] for table in tables]

        print(f" Total de tabelas encontradas: {len(table_names)}\n")
        for i, table in enumerate(table_names, 1):
            print(f"   {i}. {table}")

        print()

        # 3. Contar linhas em cada tabela
        print("=" * 60)
        print("3️  CONTANDO LINHAS EM CADA TABELA")
        print("=" * 60)
        print()

        total_rows = 0
        table_counts = {}

        for table in table_names:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
            count = cursor.fetchone()[0]
            table_counts[table] = count
            total_rows += count
            print(f"   {table:20} → {count:6} linhas")

        print()
        print(f" Total de linhas em todas as tabelas: {total_rows}\n")

        # 4. Validar estrutura de uma tabela (exemplo: customers)
        print("=" * 60)
        print("4️  VALIDANDO ESTRUTURA DA TABELA 'customers'")
        print("=" * 60)
        print()

        cursor.execute("""
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'customers'
        """, (database,))

        columns = cursor.fetchall()
        print(f" Colunas encontradas: {len(columns)}\n")

        for col in columns:
            col_name, col_type, nullable, col_key = col
            null_str = "NULL" if nullable == 'YES' else "NOT NULL"
            key_str = f"({col_key})" if col_key else ""
            print(f"   {col_name:25} {col_type:20} {null_str:10} {key_str}")

        print()

        # 5. Amostra de dados
        print("=" * 60)
        print("5️  AMOSTRA DE DADOS (Primeiros 5 clientes)")
        print("=" * 60)
        print()

        cursor.execute("""
            SELECT customerNumber, customerName, city, country
            FROM customers
            LIMIT 5
        """)

        customers = cursor.fetchall()
        for customer in customers:
            cust_num, cust_name, city, country = customer
            print(f"   {cust_num} | {cust_name:30} | {city:15} | {country}")

        print()

        # 6. Relatório final
        print("=" * 60)
        print("6️  RELATÓRIO FINAL")
        print("=" * 60)
        print()

        # Verificar integridade referencial
        cursor.execute("""
            SELECT COUNT(*) FROM customers
            WHERE salesRepEmployeeNumber IS NOT NULL
        """)
        customers_with_rep = cursor.fetchone()[0]

        print(f" Banco de dados: {database}")
        print(f" Tabelas criadas: {len(table_names)}")
        print(f" Total de registros: {total_rows}")
        print(f" Clientes com rep de vendas: {customers_with_rep}")
        print()
        print(" VALIDAÇÃO CONCLUÍDA COM SUCESSO!")
        print()

        # Salvar relatório em arquivo
        with open('validation_report.txt', 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("RELATÓRIO DE VALIDAÇÃO - CLASSICMODELS\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"Banco de dados: {database}\n")
            f.write(f"Host: {host}\n")
            f.write(f"Tabelas criadas: {len(table_names)}\n")
            f.write(f"Total de registros: {total_rows}\n\n")

            f.write("Contagem por tabela:\n")
            for table, count in table_counts.items():
                f.write(f"  {table}: {count}\n")

            f.write("\n Validação concluída com sucesso!\n")

        print(" Relatório salvo em: validation_report.txt\n")

        cursor.close()
        connection.close()

        return True

    except pymysql.Error as e:
        print(f" Erro MySQL: {str(e)}")
        return False

    except Exception as e:
        print(f" Erro geral: {str(e)}")
        return False

if __name__ == '__main__':
    success = validate_data()

    if not success:
        print(" Script 3 falhou!")
        print("   Verifique os erros acima e tente novamente.")
