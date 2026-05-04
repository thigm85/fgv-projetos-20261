import logging
import sys

import pymysql

from config import Settings, load_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


EXPECTED_ROW_COUNTS = {
    "customers": 122,
    "employees": 23,
    "offices": 7,
    "orderdetails": 2996,
    "orders": 326,
    "payments": 273,
    "productlines": 7,
    "products": 110,
}


FK_CHECKS = [
    (
        "customers.salesRepEmployeeNumber -> employees.employeeNumber",
        """
        SELECT COUNT(*) AS total
        FROM customers c
        LEFT JOIN employees e
          ON c.salesRepEmployeeNumber = e.employeeNumber
        WHERE c.salesRepEmployeeNumber IS NOT NULL
          AND e.employeeNumber IS NULL
        """,
    ),
    (
        "employees.reportsTo -> employees.employeeNumber",
        """
        SELECT COUNT(*) AS total
        FROM employees e
        LEFT JOIN employees manager
          ON e.reportsTo = manager.employeeNumber
        WHERE e.reportsTo IS NOT NULL
          AND manager.employeeNumber IS NULL
        """,
    ),
    (
        "employees.officeCode -> offices.officeCode",
        """
        SELECT COUNT(*) AS total
        FROM employees e
        LEFT JOIN offices o
          ON e.officeCode = o.officeCode
        WHERE o.officeCode IS NULL
        """,
    ),
    (
        "orders.customerNumber -> customers.customerNumber",
        """
        SELECT COUNT(*) AS total
        FROM orders o
        LEFT JOIN customers c
          ON o.customerNumber = c.customerNumber
        WHERE c.customerNumber IS NULL
        """,
    ),
    (
        "orderdetails.orderNumber -> orders.orderNumber",
        """
        SELECT COUNT(*) AS total
        FROM orderdetails od
        LEFT JOIN orders o
          ON od.orderNumber = o.orderNumber
        WHERE o.orderNumber IS NULL
        """,
    ),
    (
        "orderdetails.productCode -> products.productCode",
        """
        SELECT COUNT(*) AS total
        FROM orderdetails od
        LEFT JOIN products p
          ON od.productCode = p.productCode
        WHERE p.productCode IS NULL
        """,
    ),
    (
        "payments.customerNumber -> customers.customerNumber",
        """
        SELECT COUNT(*) AS total
        FROM payments p
        LEFT JOIN customers c
          ON p.customerNumber = c.customerNumber
        WHERE c.customerNumber IS NULL
        """,
    ),
    (
        "products.productLine -> productlines.productLine",
        """
        SELECT COUNT(*) AS total
        FROM products p
        LEFT JOIN productlines pl
          ON p.productLine = pl.productLine
        WHERE pl.productLine IS NULL
        """,
    ),
]


def connect_mysql(settings: Settings):
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    row = cursor.fetchone()
    return int(row["total"])


def validate_tables(cursor) -> list[str]:
    failures = []

    cursor.execute("SHOW TABLES;")
    found_tables = {list(row.values())[0] for row in cursor.fetchall()}
    expected_tables = set(EXPECTED_ROW_COUNTS.keys())

    missing = expected_tables - found_tables
    extra = found_tables - expected_tables

    if missing:
        failures.append(f"Tabelas ausentes: {sorted(missing)}")

    if extra:
        logger.warning("Tabelas extras encontradas: %s", sorted(extra))

    for table, expected_count in EXPECTED_ROW_COUNTS.items():
        if table not in found_tables:
            continue

        cursor.execute(f"SELECT COUNT(*) AS total FROM `{table}`;")
        actual_count = int(cursor.fetchone()["total"])

        if actual_count != expected_count:
            failures.append(
                f"Tabela {table}: esperado {expected_count}, encontrado {actual_count}"
            )
        else:
            logger.info("OK: %s possui %s linhas", table, actual_count)

    return failures


def validate_foreign_keys(cursor) -> list[str]:
    failures = []

    for description, query in FK_CHECKS:
        orphan_count = scalar(cursor, query)

        if orphan_count != 0:
            failures.append(f"FK inválida: {description} possui {orphan_count} órfãos")
        else:
            logger.info("OK: %s", description)

    return failures


def run_validation(settings: Settings) -> int:
    logger.info("Iniciando validação do banco %s", settings.db_name)

    conn = None

    try:
        conn = connect_mysql(settings)

        with conn.cursor() as cursor:
            failures = []
            failures.extend(validate_tables(cursor))
            failures.extend(validate_foreign_keys(cursor))

        if failures:
            logger.error("Validação falhou com %s erro(s):", len(failures))
            for failure in failures:
                logger.error("- %s", failure)
            return 1

        logger.info("Validação concluída com sucesso")
        return 0

    except Exception:
        logger.exception("Erro fatal na validação")
        return 1

    finally:
        if conn and conn.open:
            conn.close()
            logger.info("Conexão encerrada")


def main() -> int:
    settings = load_settings()
    return run_validation(settings)


if __name__ == "__main__":
    sys.exit(main())