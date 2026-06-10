import os
import sys

import envlocal
import mysql.connector

envlocal.load()

# com base no script de carga
TABELAS = (
    "customers",
    "employees",
    "offices",
    "orderdetails",
    "orders",
    "payments",
    "productlines",
    "products",
)
LINHAS_ESPERADAS = {
    "customers": 122,
    "employees": 23,
    "offices": 7,
    "orderdetails": 2996,
    "orders": 326,
    "payments": 273,
    "productlines": 7,
    "products": 110,
}

conn = mysql.connector.connect(
    host=os.environ["MYSQL_HOST"],
    user=os.environ.get("MYSQL_USER", "admin"),
    password=os.environ["MYSQL_PASSWORD"],
    port=int(os.environ.get("MYSQL_PORT", "3306")),
    database=os.environ.get("MYSQL_DATABASE", "classicmodels"),
)
cur = conn.cursor()

passed = 0
# verificação simples de leitura (tabelas e linhas)
for t in TABELAS:
    cur.execute(f"SELECT COUNT(*) FROM `{t}`")
    n = cur.fetchone()[0]
    esp = LINHAS_ESPERADAS[t]
    if n == esp:
        passed += 1
        print(f"  [ok]  {t:16}  {n:5} linhas (esperado {esp})")
    else:
        msg = f"{t}: obtido {n}, esperado {esp}"
        falhas.append(msg)
        print(f"  [FAIL]  {t:16}  {n:5} linhas (esperado {esp})")

cur.close()
conn.close()

print("-" * 50)
print(f"resultado: {passed}/{len(TABELAS)} verificações passed")
