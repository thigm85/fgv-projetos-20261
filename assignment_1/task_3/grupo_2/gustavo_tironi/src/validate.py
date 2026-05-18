"""
Validação do banco classicmodels no RDS MySQL.

Checks:
  1. todas as tabelas esperadas existem
  2. cada tabela tem contagem >= esperada
  3. integridade referencial (FK checks):
       - orders.customerNumber -> customers.customerNumber
       - orderdetails.orderNumber -> orders.orderNumber
       - orderdetails.productCode -> products.productCode
       - payments.customerNumber -> customers.customerNumber
       - products.productLine -> productlines.productLine
       - customers.salesRepEmployeeNumber -> employees.employeeNumber (nullable)
       - employees.officeCode -> offices.officeCode
       - employees.reportsTo -> employees.employeeNumber (nullable)

Exit code: 0 = sucesso, 1 = qualquer falha.
"""

import json
import logging
import os
import sys

import boto3
import mysql.connector
from mysql.connector import Error as MySQLError

import envlocal

envlocal.load()

SECRET_ARN = os.environ["SECRET_ARN"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
DB_NAME = "classicmodels"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("validate")

EXPECTED_ROWS = {
    "customers": 122,
    "employees": 23,
    "offices": 7,
    "orderdetails": 2996,
    "orders": 326,
    "payments": 273,
    "productlines": 7,
    "products": 110,
}

# (descrição, query). Query retorna número de órfãos (esperado: 0).
FK_CHECKS = [
    (
        "orders.customerNumber -> customers",
        """SELECT COUNT(*) FROM orders o
           LEFT JOIN customers c ON o.customerNumber = c.customerNumber
           WHERE c.customerNumber IS NULL""",
    ),
    (
        "orderdetails.orderNumber -> orders",
        """SELECT COUNT(*) FROM orderdetails od
           LEFT JOIN orders o ON od.orderNumber = o.orderNumber
           WHERE o.orderNumber IS NULL""",
    ),
    (
        "orderdetails.productCode -> products",
        """SELECT COUNT(*) FROM orderdetails od
           LEFT JOIN products p ON od.productCode = p.productCode
           WHERE p.productCode IS NULL""",
    ),
    (
        "payments.customerNumber -> customers",
        """SELECT COUNT(*) FROM payments pa
           LEFT JOIN customers c ON pa.customerNumber = c.customerNumber
           WHERE c.customerNumber IS NULL""",
    ),
    (
        "products.productLine -> productlines",
        """SELECT COUNT(*) FROM products p
           LEFT JOIN productlines pl ON p.productLine = pl.productLine
           WHERE pl.productLine IS NULL""",
    ),
    (
        "customers.salesRepEmployeeNumber -> employees",
        """SELECT COUNT(*) FROM customers c
           LEFT JOIN employees e ON c.salesRepEmployeeNumber = e.employeeNumber
           WHERE c.salesRepEmployeeNumber IS NOT NULL
             AND e.employeeNumber IS NULL""",
    ),
    (
        "employees.officeCode -> offices",
        """SELECT COUNT(*) FROM employees e
           LEFT JOIN offices o ON e.officeCode = o.officeCode
           WHERE o.officeCode IS NULL""",
    ),
    (
        "employees.reportsTo -> employees",
        """SELECT COUNT(*) FROM employees e1
           LEFT JOIN employees e2 ON e1.reportsTo = e2.employeeNumber
           WHERE e1.reportsTo IS NOT NULL
             AND e2.employeeNumber IS NULL""",
    ),
]

failures: list[str] = []


def ok(msg: str) -> None:
    log.info("  [ok]   %s", msg)


def fail(msg: str) -> None:
    log.error("  [FAIL] %s", msg)
    failures.append(msg)


def get_secret() -> dict:
    client = boto3.client("secretsmanager", region_name=REGION)
    return json.loads(client.get_secret_value(SecretId=SECRET_ARN)["SecretString"])


def connect(secret: dict):
    return mysql.connector.connect(
        host=secret["host"],
        user=secret["username"],
        password=secret["password"],
        port=int(secret["port"]),
        database=DB_NAME,
        use_pure=True,
        connection_timeout=10,
    )


def check_table_counts(cur) -> None:
    log.info("=== 1. Presença + contagem de tabelas ===")
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s",
        (DB_NAME,),
    )
    found = {row[0].lower() for row in cur.fetchall()}

    for table, expected in EXPECTED_ROWS.items():
        if table not in found:
            fail(f"{table}: tabela não existe")
            continue
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        n = cur.fetchone()[0]
        if n == expected:
            ok(f"{table:14s} {n:5d} linhas (esperado {expected})")
        else:
            fail(f"{table}: obtido {n}, esperado {expected}")


def check_foreign_keys(cur) -> None:
    log.info("=== 2. Integridade referencial ===")
    for desc, query in FK_CHECKS:
        try:
            cur.execute(query)
            orphans = cur.fetchone()[0]
            if orphans == 0:
                ok(desc)
            else:
                fail(f"{desc}: {orphans} órfão(s)")
        except MySQLError as exc:
            fail(f"{desc}: erro SQL — {exc}")


def main() -> int:
    if os.environ.get("DRY_RUN") == "1":
        log.info("DRY_RUN=1 → plano:")
        log.info("  1) validar %d tabelas com contagem esperada", len(EXPECTED_ROWS))
        log.info("  2) validar %d FK checks", len(FK_CHECKS))
        return 0

    conn = None
    try:
        log.info("Conectando ao banco %s", DB_NAME)
        secret = get_secret()
        conn = connect(secret)
        cur = conn.cursor()

        check_table_counts(cur)
        check_foreign_keys(cur)

        cur.close()
    except Exception as exc:
        log.exception("Erro durante validação: %s", exc)
        return 1
    finally:
        if conn is not None and conn.is_connected():
            conn.close()

    log.info("=" * 50)
    total = len(EXPECTED_ROWS) + len(FK_CHECKS)
    passed = total - len(failures)
    log.info("RESULTADO: %d/%d passed, %d falha(s)", passed, total, len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
