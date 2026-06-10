import json
import os
from pathlib import Path

import boto3
import mysql.connector
import envlocal

envlocal.load()

SECRET_ARN = os.environ["SECRET_ARN"]

secret = json.loads(
    boto3.client("secretsmanager", region_name="us-east-1")
    .get_secret_value(SecretId=SECRET_ARN)["SecretString"]
)

SQL_FILE = Path(__file__).resolve().parents[3] / "data" / "mysqlsampledatabase.sql"

# conecta a base de dados relacional
conn = mysql.connector.connect(
    host=secret["host"],
    user=secret["username"],
    password=secret["password"],
    port=int(secret["port"]),
    use_pure=True,
)

# carrega o script de carga
sql = SQL_FILE.read_text(encoding="utf-8", errors="replace")

for result in conn.cmd_query_iter(sql):
    if "columns" in result:
        conn.get_rows()

# finalização padrão
conn.commit()
conn.close()

print("classicmodels carregado.")
