import json
import pymysql

### Carregando as configurações

# Lendo as credenciais
with open("config/db_credentials.json", "r") as f:
    db_credentials = json.load(f)

# Lendo o endpoint gerado pela AWS
with open("config/db_endpoint.json", "r") as f:
    db_endpoint = json.load(f)


def validate_data():
    print("Conectando ao banco de dados para validação...")

    try:
        # Iniciando a conexão
        connection = pymysql.connect(
            host = db_endpoint["host"],
            port = db_endpoint["port"],
            user = db_credentials["db_user"],
            password = db_credentials["db_password"],
            database = "classicmodels",
        )

        with connection.cursor() as cursor:
            # Checando as tabelas criadas e a quantidade de registros
            print("\n--- Tabelas no banco 'classicmodels' e validação de registros ---")
            
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()

            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table[0]};")
                table_count = cursor.fetchone()[0]
                print(f" -> {table[0]}: {table_count} registros.")

        print("\nValidação concluída com sucesso.")

    except pymysql.MySQLError as e:
        print(f"\nErro no MySQL:\n{e}")
    except Exception as e:
        print(f"\nOcorreu um erro inesperado:\n{e}")
    finally:
        if "connection" in locals() and connection.open:
            connection.close()
            print("\nConexão encerrada.")

if __name__ == "__main__":
    validate_data()
