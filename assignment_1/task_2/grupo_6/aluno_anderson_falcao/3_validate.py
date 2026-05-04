"""
Validação — verifica se todas as tabelas foram criadas
e populadas corretamente no banco classicmodels
"""

import json
import os
import sys
import mysql.connector

# ---------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------
CREDENTIALS_FILE = "rds_credentials.json"
DB_NAME = "classicmodels"

# Tabelas esperadas com contagem mínima de linhas
EXPECTED_TABLES: dict[str, int] = {
    "customers":         100,
    "employees":          23,
    "offices":             7,
    "orderdetails":     2996,
    "orders":            326,
    "payments":          273,
    "productlines":        4,
    "products":          110,
}

# Checks de integridade referencial (órfãos)
# Cada tupla: (descrição, query que deve retornar 0 registros órfãos)
FK_CHECKS: list[tuple[str, str]] = [
    (
        "orders.customerNumber -> customers",
        """
        SELECT COUNT(*) FROM orders o
        LEFT JOIN customers c ON o.customerNumber = c.customerNumber
        WHERE c.customerNumber IS NULL
        """,
    ),
    (
        "orderdetails.orderNumber -> orders",
        """
        SELECT COUNT(*) FROM orderdetails od
        LEFT JOIN orders o ON od.orderNumber = o.orderNumber
        WHERE o.orderNumber IS NULL
        """,
    ),
    (
        "orderdetails.productCode -> products",
        """
        SELECT COUNT(*) FROM orderdetails od
        LEFT JOIN products p ON od.productCode = p.productCode
        WHERE p.productCode IS NULL
        """,
    ),
    (
        "payments.customerNumber -> customers",
        """
        SELECT COUNT(*) FROM payments p
        LEFT JOIN customers c ON p.customerNumber = c.customerNumber
        WHERE c.customerNumber IS NULL
        """,
    ),
    (
        "products.productLine -> productlines",
        """
        SELECT COUNT(*) FROM products p
        LEFT JOIN productlines pl ON p.productLine = pl.productLine
        WHERE pl.productLine IS NULL
        """,
    ),
    (
        "employees.officeCode -> offices",
        """
        SELECT COUNT(*) FROM employees e
        LEFT JOIN offices o ON e.officeCode = o.officeCode
        WHERE o.officeCode IS NULL
        """,
    ),
]
# -----------------------------------


def load_credentials(filepath: str) -> dict:
    if not os.path.exists(filepath):
        sys.exit(
            f"X Arquivo '{filepath}' não encontrado.\n"
            "   Execute primeiro:  python 1_provision_rds.py"
        )
    with open(filepath) as f:
        return json.load(f)


def connect(creds: dict):
    return mysql.connector.connect(
        host=creds["host"],
        port=int(creds["port"]),
        user=creds["username"],
        password=creds["password"],
        database=DB_NAME,
        connection_timeout=10,
    )


def section(title: str) -> None:
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


def check_tables(cur) -> tuple[list[str], list[str], list[str]]:
    cur.execute("SHOW TABLES;")
    found = {row[0].lower() for row in cur.fetchall()}
    expected = set(EXPECTED_TABLES.keys())
    present = sorted(found & expected)
    extra   = sorted(found - expected)
    missing = sorted(expected - found)
    return present, extra, missing


def check_row_counts(cur, tables: list[str]) -> dict[str, dict]:
    results = {}
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM `{table}`;")
        actual = cur.fetchone()[0]
        expected = EXPECTED_TABLES.get(table, 0)
        ok = actual >= expected
        results[table] = {"actual": actual, "expected": expected, "ok": ok}
    return results


def check_foreign_keys(cur) -> list[dict]:
    """
    NOVO: verifica integridade referencial buscando registros órfãos.
    Cada check deve retornar 0 para passar.
    """
    results = []
    for desc, query in FK_CHECKS:
        try:
            cur.execute(query)
            orphans = cur.fetchone()[0]
            ok = orphans == 0
            results.append({"name": desc, "orphans": orphans, "ok": ok})
        except mysql.connector.Error as e:
            results.append({"name": desc, "orphans": -1, "ok": False, "error": str(e)})
    return results


def check_sample_queries(cur) -> list[dict]:
    queries = [
        {
            "name":  "Receita total por linha de produto",
            "sql":   """
                SELECT pl.productLine, SUM(od.quantityOrdered * od.priceEach) AS revenue
                FROM   orderdetails od
                JOIN   products     p  ON od.productCode   = p.productCode
                JOIN   productlines pl ON p.productLine     = pl.productLine
                GROUP  BY pl.productLine
                ORDER  BY revenue DESC
                LIMIT  3;
            """,
        },
        {
            "name":  "Top 3 clientes por valor pago",
            "sql":   """
                SELECT c.customerName, SUM(p.amount) AS total_paid
                FROM   payments  p
                JOIN   customers c ON p.customerNumber = c.customerNumber
                GROUP  BY c.customerNumber, c.customerName
                ORDER  BY total_paid DESC
                LIMIT  3;
            """,
        },
        {
            "name":  "Pedidos por status",
            "sql":   """
                SELECT status, COUNT(*) AS qty
                FROM   orders
                GROUP  BY status
                ORDER  BY qty DESC;
            """,
        },
    ]
    results = []
    for q in queries:
        try:
            cur.execute(q["sql"])
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            results.append({"name": q["name"], "cols": cols, "rows": rows, "ok": True})
        except mysql.connector.Error as e:
            results.append({"name": q["name"], "error": str(e), "ok": False})
    return results


def print_table(cols: list[str], rows: list[tuple]) -> None:
    widths = [max(len(str(c)), max((len(str(r[i])) for r in rows), default=0))
              for i, c in enumerate(cols)]
    sep    = "  " + "  ".join("-" * w for w in widths)
    header = "  " + "  ".join(str(c).ljust(w) for c, w in zip(cols, widths))
    print(header)
    print(sep)
    for row in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(row, widths)))


def main():
    print("=" * 55)
    print("  Validação do banco classicmodels — RDS MySQL")
    print("=" * 55)

    creds = load_credentials(CREDENTIALS_FILE)
    print(f"\n  Host    : {creds['host']}:{creds['port']}")
    print(f"  Banco   : {DB_NAME}")
    print(f"  Usuário : {creds['username']}")

    try:
        conn = connect(creds)
        cur = conn.cursor()
        print("\n  OK Conexão estabelecida com sucesso.")
    except mysql.connector.Error as e:
        sys.exit(f"\nX Falha na conexão: {e}")

    all_ok = True

    # -- 1. Tabelas ---------------------
    section("1. Verificação de tabelas")
    present, extra, missing = check_tables(cur)

    if missing:
        all_ok = False
        print(f"  X Tabelas FALTANDO ({len(missing)}): {', '.join(missing)}")
    else:
        print(f"  OK Todas as {len(EXPECTED_TABLES)} tabelas esperadas estão presentes.")

    if extra:
        print(f"     Tabelas extras (não esperadas): {', '.join(extra)}")

    # -- 2. Contagem de linhas ---------
    section("2. Contagem de linhas por tabela")
    counts = check_row_counts(cur, present)

    col_w = max(len(t) for t in present) + 2 if present else 14
    print(f"  {'Tabela'.ljust(col_w)} {'Esperado':>10}  {'Encontrado':>10}  Status")
    print(f"  {'─'*col_w} {'─'*10}  {'─'*10}  {'─'*6}")
    for table, info in counts.items():
        status = "OK" if info["ok"] else "X BAIXO"
        if not info["ok"]:
            all_ok = False
        print(
            f"  {table.ljust(col_w)} {info['expected']:>10}  "
            f"{info['actual']:>10}  {status}"
        )

    # -- 3. Integridade referencial (FK) -----
    section("3. Integridade referencial (órfãos)")
    fk_results = check_foreign_keys(cur)

    for r in fk_results:
        if r.get("error"):
            all_ok = False
            print(f"  X {r['name']}: erro — {r['error']}")
        elif r["ok"]:
            print(f"  OK {r['name']}: sem órfãos")
        else:
            all_ok = False
            print(f"  X {r['name']}: {r['orphans']} registro(s) órfão(s)")

    # -- 4. Queries de negócio --------------
    section("4. Queries de integridade / negócio")
    sample_results = check_sample_queries(cur)

    for qr in sample_results:
        print(f"\n    {qr['name']}")
        if qr["ok"]:
            print_table(qr["cols"], qr["rows"])
        else:
            all_ok = False
            print(f"  X Erro: {qr['error']}")

    # -- Resultado final ------------------
    section("RESULTADO FINAL")
    if all_ok:
        print("  OK Banco classicmodels validado com sucesso!")
        print("     O RDS está pronto para ser usado como origem do pipeline.")
    else:
        print("  X Foram encontrados problemas — revise os itens acima.")
        print("     Tente re-executar:  python 2_load_data.py")

    cur.close()
    conn.close()
    print("=" * 55)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()