import json
import pymysql
from pymysql.constants import CLIENT
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

    print(f" Informações do RDS carregadas:")
    print(f"  Host: {host}")
    print(f"  User: {user}")
    print(f"  Port: {port}")
    print(f"  Database: {database}")

except FileNotFoundError:
    print(" Arquivo rds_info.json não encontrado!")
    print("   Execute primeiro o script 1_provision_rds.py")
    exit(1)

def load_sql_data():
    """
    Carrega os dados do arquivo SQL no RDS
    """
    try:
        print("\n Conectando ao RDS...")

        # Conectar ao RDS com suporte a múltiplos statements
        connection = pymysql.connect(
            host=host,
            user=user,
            password=password,
            port=port,
            client_flag=CLIENT.MULTI_STATEMENTS
        )

        cursor = connection.cursor()
        print(" Conectado ao RDS c")

        # Ler arquivo SQL
        sql_file_path = Path(__file__).parent.parent.parent / 'data' / 'mysqlsampledatabase.sql'

        print(f"\n Lendo arquivo SQL de: {sql_file_path}")

        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        print(" Arquivo SQL lido")

        # Executar todos os comandos SQL de uma vez
        print(f"\n Executando SQL...")

        # Iterar sobre todos os resultados gerados pelo MULTI_STATEMENTS
        cursor.execute(sql_content)
        while cursor.nextset():
            pass

        # Confirmar todas as mudanças
        print("\n Confirmando mudanças no banco...")
        connection.commit()

        print(f"\n SQL executado")
        print(" Dados carregados no RDS!")

        cursor.close()
        connection.close()

        return True

    except FileNotFoundError:
        print(f" Arquivo SQL não encontrado em: {sql_file_path}")
        return False

    except pymysql.Error as e:
        print(f" Erro MySQL: {str(e)}")
        return False

    except Exception as e:
        print(f" Erro geral: {str(e)}")
        return False

if __name__ == '__main__':
    success = load_sql_data()

    if success:
        print("\n Script 2 concluído com sucesso!")
        print("   Próximo: Execute o script 3_validate_data.py")
    else:
        print("\n Script 2 falhou!")
        print("   Verifique os erros acima e tente novamente.")