"""
Validação - verifica se todas as tabelas foram criadas
e populadas corretamente no banco classicmodels
Integra-se com outputs do Terraform para pegar o endpoint.
"""

import json
import os
import sys
import subprocess
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------
DB_NAME = "classicmodels"

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

FK_CHECKS: list[tuple[str, str]] = [
    ("orders.customerNumber -> customers", "SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON o.customerNumber = c.customerNumber WHERE c.customerNumber IS NULL"),
    ("orderdetails.orderNumber -> orders", "SELECT COUNT(*) FROM orderdetails od LEFT JOIN orders o ON od.orderNumber = o.orderNumber WHERE o.orderNumber IS NULL"),
    ("orderdetails.productCode -> products", "SELECT COUNT(*) FROM orderdetails od LEFT JOIN products p ON od.productCode = p.productCode WHERE p.productCode IS NULL"),
    ("payments.customerNumber -> customers", "SELECT COUNT(*) FROM payments p LEFT JOIN customers c ON p.customerNumber = c.customerNumber WHERE c.customerNumber IS NULL"),
    ("products.productLine -> productlines", "SELECT COUNT(*) FROM products p LEFT JOIN productlines pl ON p.productLine = pl.productLine WHERE pl.productLine IS NULL"),
    ("employees.officeCode -> offices", "SELECT COUNT(*) FROM employees e LEFT JOIN offices o ON e.officeCode = o.officeCode WHERE o.officeCode IS NULL"),
]

def get_terraform_outputs() -> dict:
    tf_dir = os.path.join(os.path.dirname(__file__), "..", "terraform")
    try:
        res = subprocess.run(["terraform", "output", "-json"], cwd=tf_dir, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        sys.exit(f"X Erro ao rodar terraform output: {e.stderr}")

def get_credentials() -> dict:
    outputs = get_terraform_outputs()
    host = outputs.get("rds_endpoint", {}).get("value")
    port = outputs.get("rds_port", {}).get("value", 3306)
    
    username = os.getenv("TF_VAR_db_username") or os.getenv("USERNAME")
    password = os.getenv("TF_VAR_db_password") or os.getenv("PASSWORD")
    
    if not host or not username or not password:
        sys.exit("X Credenciais incompletas. Verifique Terraform e .env.")

    return {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password
    }


def connect(creds: dict):
    return mysql.connector.connect(
        host=creds["host"],
        port=creds["port"],
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

def main():
    print("=" * 55)
    print("  Validação do banco classicmodels - RDS MySQL")
    print("=" * 55)

    creds = get_credentials()
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

    section("1. Verificação de tabelas")
    present, extra, missing = check_tables(cur)
    if missing:
        all_ok = False
        print(f"  X Tabelas FALTANDO ({len(missing)}): {', '.join(missing)}")
    else:
        print(f"  OK Todas as {len(EXPECTED_TABLES)} tabelas esperadas estão presentes.")
    if extra:
        print(f"     Tabelas extras (não esperadas): {', '.join(extra)}")

    section("2. Contagem de linhas por tabela")
    counts = check_row_counts(cur, present)
    col_w = max(len(t) for t in present) + 2 if present else 14
    print(f"  {'Tabela'.ljust(col_w)} {'Esperado':>10}  {'Encontrado':>10}  Status")
    print(f"  {'─'*col_w} {'─'*10}  {'─'*10}  {'─'*6}")
    for table, info in counts.items():
        status = "OK" if info["ok"] else "X BAIXO"
        if not info["ok"]: all_ok = False
        print(f"  {table.ljust(col_w)} {info['expected']:>10}  {info['actual']:>10}  {status}")

    section("3. Integridade referencial (órfãos)")
    fk_results = check_foreign_keys(cur)
    for r in fk_results:
        if r.get("error"):
            all_ok = False
            print(f"  X {r['name']}: erro - {r['error']}")
        elif r["ok"]:
            print(f"  OK {r['name']}: sem órfãos")
        else:
            all_ok = False
            print(f"  X {r['name']}: {r['orphans']} registro(s) órfão(s)")

    section("RESULTADO FINAL")
    if all_ok:
        print("  OK Banco classicmodels validado com sucesso!")
    else:
        print("  X Foram encontrados problemas - revise os itens acima.")

    cur.close()
    conn.close()
    print("=" * 55)
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
