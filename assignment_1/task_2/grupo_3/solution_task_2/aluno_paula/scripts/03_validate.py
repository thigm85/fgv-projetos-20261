import os
import sys

import mysql.connector

"""Script 03: validacao com quality gates objetivos e exit code deterministico."""


def env_any(names, default=None, required=False):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and default is None:
        raise RuntimeError(f"Variavel obrigatoria ausente: {', '.join(names)}")
    return default


def log(step: str, msg: str) -> None:
    print(f"[{step}] {msg}")


def split_host_port(raw_host: str, raw_port: str):
    # Normaliza host/porta para evitar erro de DNS com "host:porta".
    host = raw_host.strip()
    port = int(raw_port)
    if ":" in host:
        maybe_host, maybe_port = host.rsplit(":", 1)
        if maybe_port.isdigit():
            host = maybe_host
            port = int(maybe_port)
    return host, port


try:
    host = env_any(["DB_HOST"], required=True)
    user = env_any(["DB_USER", "DB_USERNAME"], required=True)
    password = env_any(["DB_PASSWORD"], required=True)
except RuntimeError as exc:
    print(f"[ERRO] {exc}")
    sys.exit(1)

database = env_any(["DB_NAME"], default="classicmodels")
port = env_any(["DB_PORT"], default="3306")
host, port = split_host_port(host, port)

conn = mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)

cursor = conn.cursor()
failures = []

log("1/4", f"Validando tabelas esperadas no schema '{database}'.")
cursor.execute("SHOW TABLES;")
tables = sorted([t[0] for t in cursor.fetchall()])

expected_tables = [
    "customers",
    "employees",
    "offices",
    "orderdetails",
    "orders",
    "payments",
    "productlines",
    "products",
]

missing_tables = [table for table in expected_tables if table not in tables]
if missing_tables:
    # Guarda falhas para decidir o exit code ao final.
    failures.append({"type": "missing_tables", "value": missing_tables})

thresholds = {
    "customers": 1,
    "employees": 1,
    "offices": 1,
    "orders": 1,
    "orderdetails": 1,
    "payments": 1,
    "productlines": 1,
    "products": 1,
}

log("2/4", "Validando contagem minima por tabela critica.")
for table, minimum in thresholds.items():
    if table not in tables:
        continue
    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
    count = cursor.fetchone()[0]
    print(f"{table}: {count} linha(s)")
    if count < minimum:
        failures.append({"type": "min_rows", "table": table, "count": count, "minimum": minimum})

fk_checks = [
    ("orders.customerNumber -> customers.customerNumber", {"orders", "customers"},
     """
     SELECT COUNT(*)
     FROM orders o
     LEFT JOIN customers c ON c.customerNumber = o.customerNumber
     WHERE c.customerNumber IS NULL
     """),
    ("orderdetails.orderNumber -> orders.orderNumber", {"orderdetails", "orders"},
     """
     SELECT COUNT(*)
     FROM orderdetails od
     LEFT JOIN orders o ON o.orderNumber = od.orderNumber
     WHERE o.orderNumber IS NULL
     """),
    ("orderdetails.productCode -> products.productCode", {"orderdetails", "products"},
     """
     SELECT COUNT(*)
     FROM orderdetails od
     LEFT JOIN products p ON p.productCode = od.productCode
     WHERE p.productCode IS NULL
     """),
]

log("3/4", "Validando integridade referencial basica.")
for desc, required_tables, query in fk_checks:
    # Só executa FK check se as tabelas necessárias existirem.
    missing_for_check = sorted([t for t in required_tables if t not in tables])
    if missing_for_check:
        failures.append({"type": "fk_check_skipped_missing_tables", "check": desc, "missing": missing_for_check})
        continue
    cursor.execute(query)
    orphans = cursor.fetchone()[0]
    print(f"{desc}: orfaos={orphans}")
    if orphans != 0:
        failures.append({"type": "fk_orphans", "check": desc, "orphans": orphans})

cursor.close()
conn.close()

if failures:
    log("4/4", "Falha na validacao de qualidade.")
    for item in failures:
        print(f"[FAIL] {item}")
    sys.exit(1)

log("4/4", "Validacao concluida com sucesso.")
