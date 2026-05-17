import pymysql
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
args = parser.parse_args()

conn = pymysql.connect(
    host=args.host,
    user="admin",
    password="Admin1234!",
    database="classicmodels"
)

cursor = conn.cursor()

cursor.execute("SHOW TABLES;")
tables = cursor.fetchall()

print("Tabelas:")
for t in tables:
    print(t)

cursor.execute("SELECT COUNT(*) FROM customers;")
print("Customers:", cursor.fetchone()[0])