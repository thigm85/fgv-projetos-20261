import pymysql
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
parser.add_argument("--sql-file", default="mysqlsampledatabase.sql")
args = parser.parse_args()

conn = pymysql.connect(
    host=args.host,
    user="admin",
    password="Admin1234!",
    autocommit=True
)

cursor = conn.cursor()

with open(args.sql_file, "r") as f:
    sql = f.read()

for statement in sql.split(";"):
    if statement.strip():
        cursor.execute(statement)

print("Banco carregado com sucesso!")