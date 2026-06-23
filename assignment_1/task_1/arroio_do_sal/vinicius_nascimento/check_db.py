import pymysql

HOST = "classicmodels.c3aoiiqs8yhu.us-east-1.rds.amazonaws.com"
USER = "admin"
PASSWORD = "ArianaGrande123!"

def validate():
    conn = pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database="classicmodels"
    )

    cursor = conn.cursor()

    print("Listando tabelas...")

    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    for t in tables:
        name = t[0]
        cursor.execute(f"SELECT COUNT(*) FROM {name}")
        count = cursor.fetchone()[0]
        print(f"{name}: {count} linhas")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    validate()