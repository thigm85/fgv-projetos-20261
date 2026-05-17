from __future__ import annotations

import argparse
import sys
from typing import List, Sequence

from lib_mysql import MySqlConnInfo, query_all, query_one


EXPECTED_TABLES: Sequence[str] = (
    "customers",
    "products",
    "productlines",
    "orders",
    "orderdetails",
    "payments",
    "employees",
    "offices",
)


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Valida se o banco classicmodels foi carregado corretamente.")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    args = p.parse_args(argv)

    info = MySqlConnInfo(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database="classicmodels",
    )

    rows = query_all(
        info=info,
        query=(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name"
        ),
        params=("classicmodels",),
    )
    found = {r[0] for r in rows}
    missing = [t for t in EXPECTED_TABLES if t not in found]
    if missing:
        print(f"Faltando tabelas: {missing}", file=sys.stderr)
        return 2

    checks = {}
    for t in ("customers", "orders", "orderdetails", "payments", "products"):
        c = query_one(info=info, query=f"SELECT COUNT(*) FROM {t}")
        checks[t] = int(c[0])

    print("OK: tabelas esperadas presentes.")
    print("Contagens (amostra):")
    for k, v in checks.items():
        print(f"- {k}: {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

