#!/usr/bin/env python3
import os
import sys
import pymysql
import pymysql.cursors

failures = 0

def ok(msg): print(f"[OK] {msg}")

def fail(msg):
    global failures
    failures += 1
    print(f"[FALHA] {msg}")

def section(title: str):
    print(f"\n=== {title} ===")

def info(msg): print(f"[INFO] {msg}")
def warn(msg): print(f"[AVISO] {msg}")
def error(msg): print(f"[ERRO] {msg}"); raise SystemExit(1)

EXPECTED_TABLES = {
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
        "orders.customerNumber -> customers",
        """SELECT COUNT(*) FROM orders o
           LEFT JOIN customers c ON o.customerNumber = c.customerNumber
           WHERE c.customerNumber IS NULL"""
    ),
    (
        "orderdetails.orderNumber -> orders",
        """SELECT COUNT(*) FROM orderdetails od
           LEFT JOIN orders o ON od.orderNumber = o.orderNumber
           WHERE o.orderNumber IS NULL"""
    ),
    (
        "orderdetails.productCode -> products",
        """SELECT COUNT(*) FROM orderdetails od
           LEFT JOIN products p ON od.productCode = p.productCode
           WHERE p.productCode IS NULL"""
    ),
    (
        "payments.customerNumber -> customers",
        """SELECT COUNT(*) FROM payments py
           LEFT JOIN customers c ON py.customerNumber = c.customerNumber
           WHERE c.customerNumber IS NULL"""
    ),
    (
        "employees.officeCode -> offices",
        """SELECT COUNT(*) FROM employees e
           LEFT JOIN offices o ON e.officeCode = o.officeCode
           WHERE o.officeCode IS NULL"""
    ),
    (
        "products.productLine -> productlines",
        """SELECT COUNT(*) FROM products p
           LEFT JOIN productlines pl ON p.productLine = pl.productLine
           WHERE pl.productLine IS NULL"""
    ),
]

def load_env(filepath: str = "rds_connection.env") -> dict:
    env = {}
    if os.path.isfile(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip()

    return {
        "host":     env.get("RDS_HOST",     os.environ.get("RDS_HOST",     "ENDPOINT")),
        "port":     int(env.get("RDS_PORT", os.environ.get("RDS_PORT",     "3306"))),
        "db":       env.get("RDS_DB",       os.environ.get("RDS_DB",       "classicmodels")),
        "user":     env.get("RDS_USER",     os.environ.get("RDS_USER",     "admin")),
        "password": env.get("RDS_PASSWORD", os.environ.get("RDS_PASSWORD", "")),
    }


def get_connection(cfg: dict) -> pymysql.Connection:
    return pymysql.connect(
        host            = cfg["host"],
        port            = cfg["port"],
        user            = cfg["user"],
        password        = cfg["password"],
        database        = cfg["db"],
        connect_timeout = 15,
        charset         = "utf8mb4",
        cursorclass     = pymysql.cursors.DictCursor,
    )


def scalar(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return list(row.values())[0] if row else None


def fetchall(conn, sql: str, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def check_connectivity(conn, cfg: dict):
    section("1. Conectividade")
    result = scalar(conn, "SELECT VERSION()")
    ok(f"Conexão com RDS ({cfg['host']}:{cfg['port']}) estabelecida")
    ok(f"Versão do servidor: MySQL {result}")

def check_tables(conn, cfg: dict):
    section("2. Tabelas esperadas")
    missing = 0
    for table in EXPECTED_TABLES:
        exists = scalar(
            conn,
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (cfg["db"], table),
        )
        if exists:
            ok(f"Tabela '{table}' existe")
        else:
            fail(f"Tabela '{table}' NÃO encontrada")
            missing += 1

    if missing == 0:
        ok("Todas as tabelas foram encontradas")
    else:
        warn(f"{missing} tabela(s) ausente(s)")

def check_row_counts(conn):
    section("3. Contagem de linhas")

    header = f"{'Tabela':<20} {'Esperado':>10}  {'Encontrado':>10}  Status"
    sep    = "-" * 56
    print(f"  {header}")
    print(f"  {sep}")

    for table, min_expected in EXPECTED_TABLES.items():
        count = scalar(conn, f"SELECT COUNT(*) FROM `{table}`")
        if count >= min_expected:
            status = f"OK"
        else:
            status = f"ABAIXO DO ESPERADO"
            global failures
            failures += 1
        print(f"  {table:<20} {min_expected:>10}  {count:>10}  {status}")

def check_foreign_keys(conn):
    section("4. Integridade referencial")
    for desc, query in FK_CHECKS:
        orphans = scalar(conn, query)
        if orphans == 0:
            ok(desc)
        else:
            fail(f"{desc} -> {orphans} registro(s) órfão(s)")


def run_business_queries(conn):
    section("5. Queries exemplo")

    print(f"\n Top 5 clientes por valor total de pedidos:\n")
    rows = fetchall(conn, """
        SELECT
            c.customerName                                   AS Cliente,
            COUNT(DISTINCT o.orderNumber)                    AS Pedidos,
            FORMAT(SUM(od.quantityOrdered * od.priceEach),2) AS Total
        FROM customers c
        JOIN orders o        ON o.customerNumber  = c.customerNumber
        JOIN orderdetails od ON od.orderNumber    = o.orderNumber
        GROUP BY c.customerName
        ORDER BY SUM(od.quantityOrdered * od.priceEach) DESC
        LIMIT 5
    """)
    col_w = [30, 10, 15]
    hdrs  = ["Cliente", "Pedidos", "Total"]
    _print_table(hdrs, [(r["Cliente"], r["Pedidos"], r["Total"]) for r in rows], col_w)

    print(f"\n Receita por linha de produto:\n")
    rows = fetchall(conn, """
        SELECT
            pl.productLine                                   AS Linha,
            COUNT(DISTINCT p.productCode)                    AS Produtos,
            FORMAT(SUM(od.quantityOrdered * od.priceEach),2) AS Receita
        FROM productlines pl
        JOIN products     p  ON p.productLine  = pl.productLine
        JOIN orderdetails od ON od.productCode = p.productCode
        GROUP BY pl.productLine
        ORDER BY SUM(od.quantityOrdered * od.priceEach) DESC
    """)
    col_w = [22, 10, 18]
    hdrs  = ["Linha", "Produtos", "Receita"]
    _print_table(hdrs, [(r["Linha"], r["Produtos"], r["Receita"]) for r in rows], col_w)

def check_business_rules(conn):
    section("6. Regras de negócio")
    checks = [
        ("Preço de compra negativo",     "SELECT COUNT(*) FROM products WHERE buyPrice <= 0"),
        ("MSRP menor que custo",         "SELECT COUNT(*) FROM products WHERE MSRP < buyPrice"),
        ("Quantidade em estoque negativa","SELECT COUNT(*) FROM products WHERE quantityInStock < 0"),
        ("Pagamentos com valor zero",    "SELECT COUNT(*) FROM payments WHERE amount <= 0"),
        ("Pedidos sem data de envio (exceto cancelados/em processo)",
         "SELECT COUNT(*) FROM orders WHERE shippedDate IS NULL AND status = 'Shipped'"),
        ("Credit limit negativo",        "SELECT COUNT(*) FROM customers WHERE creditLimit < 0"),
    ]
    for desc, query in checks:
        n = scalar(conn, query)
        if n == 0:
            ok(desc)
        else:
            fail(f"{desc} -> {n} ocorrência(s)")

def check_duplicates(conn):
    section("7. Campos únicos duplicados")
    checks = [
        ("customers.customerName",   "SELECT COUNT(*) FROM (SELECT customerName FROM customers GROUP BY customerName HAVING COUNT(*) > 1) t"),
        ("payments.checkNumber",     "SELECT COUNT(*) FROM (SELECT checkNumber FROM payments GROUP BY checkNumber HAVING COUNT(*) > 1) t"),
    ]
    for desc, query in checks:
        n = scalar(conn, query)
        if n == 0:
            ok(f"{desc} sem duplicatas")
        else:
            fail(f"{desc} -> {n} valor(es) duplicado(s)")


def _print_table(headers: list, rows: list, widths: list):
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    sep = "  " + "  ".join("─" * w for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))


def print_result(cfg: dict):
    section("8. Resultado final")
    if failures == 0:
        print("Todas as validações passaram")
    else:
        print(f"{failures} validação(ões) falharam")
        raise SystemExit(1)

def main():
    print(f"Validando classicmodels")

    cfg = load_env()

    try:
        conn = get_connection(cfg)
    except pymysql.err.OperationalError as e:
        error(f"Não foi possível conectar ao RDS: {e}")

    check_connectivity(conn, cfg)
    check_tables(conn, cfg)
    check_row_counts(conn)
    check_foreign_keys(conn)
    run_business_queries(conn)
    check_business_rules(conn)
    check_duplicates(conn)   

    conn.close()
    print_result(cfg)

if __name__ == "__main__":
    main()