"""
Valida o banco classicmodels no RDS: tabelas, contagens mínimas e integridade referencial.
Exit code 0 = aprovado, 1 = reprovado.
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import pymysql

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# --- Configuração ---

def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"[ERRO] Variável de ambiente obrigatória não definida: {name}")
        sys.exit(1)
    return value

RDS_ADMIN_PASSWORD = require_env("RDS_ADMIN_PASSWORD")

info_path = BASE_DIR / "pipeline_info.json"
if not info_path.exists():
    print("[ERRO] pipeline_info.json não encontrado. Execute 'terraform apply' primeiro.")
    sys.exit(1)

info = json.loads(info_path.read_text())
RDS_ENDPOINT   = info["rds_endpoint"]
RDS_PORT       = int(info["rds_port"])
RDS_ADMIN_USER = info["rds_admin_user"]
RDS_DB_NAME    = info["rds_db_name"]

# Contagens mínimas esperadas por tabela
EXPECTED_COUNTS = {
    "customers":    122,
    "employees":    23,
    "offices":      7,
    "orderdetails": 2996,
    "orders":       326,
    "payments":     273,
    "productlines": 7,
    "products":     110,
}

# Checks de integridade referencial
FK_CHECKS = [
    (
        "orders → customers",
        "SELECT COUNT(*) FROM orders o "
        "LEFT JOIN customers c ON o.customerNumber = c.customerNumber "
        "WHERE c.customerNumber IS NULL",
    ),
    (
        "orderdetails → orders",
        "SELECT COUNT(*) FROM orderdetails od "
        "LEFT JOIN orders o ON od.orderNumber = o.orderNumber "
        "WHERE o.orderNumber IS NULL",
    ),
    (
        "orderdetails → products",
        "SELECT COUNT(*) FROM orderdetails od "
        "LEFT JOIN products p ON od.productCode = p.productCode "
        "WHERE p.productCode IS NULL",
    ),
    (
        "payments → customers",
        "SELECT COUNT(*) FROM payments p "
        "LEFT JOIN customers c ON p.customerNumber = c.customerNumber "
        "WHERE c.customerNumber IS NULL",
    ),
]

MAX_RETRIES = 5
PASS = "[PASS]"
FAIL = "[FAIL]"


def check(condition: bool, msg: str, failures: list) -> None:
    label = PASS if condition else FAIL
    print(f"  {label} {msg}")
    if not condition:
        failures.append(msg)


def scalar(cursor, sql: str) -> int:
    cursor.execute(sql)
    return cursor.fetchone()[0]


def main() -> int:
    failures = []
    conn = None

    print("=" * 55)
    print("Passo 1/4 — Conectando ao RDS")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            conn = pymysql.connect(
                host=RDS_ENDPOINT,
                port=RDS_PORT,
                user=RDS_ADMIN_USER,
                password=RDS_ADMIN_PASSWORD,
                database=RDS_DB_NAME,
                connect_timeout=10,
            )
            print(f"  Conectado a {RDS_ENDPOINT}:{RDS_PORT}/{RDS_DB_NAME}")
            break
        except Exception as exc:
            if "Unknown database" in str(exc):
                print("[ERRO] O banco 'classicmodels' não existe. Execute '2_load_data.py' primeiro.")
                return 1
            if attempt == MAX_RETRIES:
                print(f"[ERRO] Falha após {MAX_RETRIES} tentativas: {exc}")
                return 1
            wait = 2 ** attempt
            print(f"  [{attempt}/{MAX_RETRIES}] Falha: {exc}. Aguardando {wait}s...")
            time.sleep(wait)

    try:
        with conn.cursor() as cur:

            # --- Passo 2: Tabelas existem? ---
            print("\nPasso 2/4 — Verificando tabelas")
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s",
                (RDS_DB_NAME,),
            )
            existing = {row[0] for row in cur.fetchall()}
            for table in EXPECTED_COUNTS:
                check(table in existing, f"Tabela '{table}' existe", failures)

            # --- Passo 3: Contagens mínimas ---
            print("\nPasso 3/4 — Verificando contagens")
            for table, minimum in EXPECTED_COUNTS.items():
                if table not in existing:
                    continue
                count = scalar(cur, f"SELECT COUNT(*) FROM `{table}`")
                check(
                    count >= minimum,
                    f"{table}: {count} linhas (mínimo esperado: {minimum})",
                    failures,
                )

            # --- Passo 4: Integridade referencial ---
            print("\nPasso 4/4 — Verificando integridade referencial")
            for desc, query in FK_CHECKS:
                orphans = scalar(cur, query)
                check(
                    orphans == 0,
                    f"FK {desc}: {orphans} registro(s) órfão(s)",
                    failures,
                )

    finally:
        conn.close()
        print("\n  Conexão encerrada.")

    # --- Resultado ---
    print("\n" + "=" * 55)
    if failures:
        print(f"REPROVADO — {len(failures)} verificação(ões) falharam:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("APROVADO — todas as verificações passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
