import json
import pymysql
from pymysql.constants import CLIENT

### Carregando as configurações

# Lendo as credenciais
with open("config/db_credentials.json", "r") as f:
    db_credentials = json.load(f)

# Lendo o endpoint gerado pela AWS
with open("config/db_endpoint.json", "r") as f:
    db_endpoint = json.load(f)


# Caminho do arquivo SQL
SQL_FILE_PATH = "../../data/mysqlsampledatabase.sql"

def load_data():
    print(f"Conectando ao banco em {db_endpoint['host']}...")

    try:
        # Iniciando a conexão
        connection = pymysql.connect(
            host = db_endpoint["host"],
            port = db_endpoint["port"],
            user = db_credentials["db_user"],
            password = db_credentials["db_password"],
            client_flag = CLIENT.MULTI_STATEMENTS,
            autocommit = True,
        )

        print("Conexão bem-sucedida. Lendo o arquivo SQL...")

        with open(SQL_FILE_PATH, "r", encoding = "utf-8") as f:
            sql_script = f.read()

        print("Executando o script SQL...")

        with connection.cursor() as cursor:
            cursor.execute(sql_script)

        print("\nDados carregados com sucesso. Banco populado.")

    except FileNotFoundError:
        print(f"\nErro: O arquivo SQL não foi encontrado no caminho: {SQL_FILE_PATH}.")
    except pymysql.MySQLError as e:
        print(f"\nErro no MySQL:\n{e}")
    except Exception as e:
        print(f"\nOcorreu um erro inesperado:\n{e}")
    finally:
        # Garantindo que a conexão será fechada mesmo se houver erro
        if "connection" in locals() and connection.open:
            connection.close()
            print("Conexão encerrada.")

if __name__ == "__main__":
    load_data()