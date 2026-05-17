from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from lib_mysql import MySqlConnInfo, execute_sql_file


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Cria e popula o banco classicmodels a partir de um arquivo .sql")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--sql-path", required=True, help="Caminho para mysqlsampledatabase.sql")
    args = p.parse_args(argv)

    sql_path = Path(args.sql_path).expanduser().resolve()
    if not sql_path.exists():
        print(f"SQL não encontrado em: {sql_path}", file=sys.stderr)
        return 2

    info = MySqlConnInfo(host=args.host, port=args.port, user=args.user, password=args.password)
    execute_sql_file(info=info, sql_path=sql_path)
    print("Carga concluída com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

