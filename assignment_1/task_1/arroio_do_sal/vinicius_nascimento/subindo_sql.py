import pymysql
from pymysql.constants import CLIENT

HOST = "classicmodels.c3aoiiqs8yhu.us-east-1.rds.amazonaws.com"
USER = "admin"
PASSWORD = "ArianaGrande123!"

SQL_PATH = "../../data/mysqlsampledatabase.sql"

def run_sql_script():
    print("Conectando ao banco...")

    conn = pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        autocommit=True
    )

    cursor = conn.cursor()

    print("Lendo arquivo SQL...")

    with open(SQL_PATH, "r", encoding="utf-8") as f:
        script = f.read()

    print("Executando script...")

    conn = pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        autocommit=True,
        client_flag=CLIENT.MULTI_STATEMENTS
    )

    cursor = conn.cursor()

    cursor.execute(script)

    print("Carga finalizada!")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    run_sql_script()