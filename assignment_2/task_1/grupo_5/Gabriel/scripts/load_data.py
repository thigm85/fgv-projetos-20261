import os
import sys
import re
import pymysql

RDS_HOST = os.environ["RDS_HOST"]
RDS_PORT = int(os.environ.get("RDS_PORT", 3306))
RDS_USER = os.environ["RDS_USER"]
RDS_PASSWORD = os.environ["RDS_PASSWORD"]

SQL_FILE = os.environ.get(
    "SQL_FILE",
    os.path.join(
        os.path.dirname(__file__),
        "../../../../..",
        "assignment_1/task_1/data/mysqlsampledatabase.sql",
    ),
)


def split_statements(sql_text: str) -> list[str]:
    statements = []
    current = []
    delimiter = ";"

    for line in sql_text.splitlines():
        stripped = line.strip()

        if stripped.upper().startswith("DELIMITER"):
            delimiter = stripped.split()[1]
            continue

        current.append(line)

        if stripped.endswith(delimiter):
            stmt = "\n".join(current).strip()
            if delimiter != ";":
                stmt = stmt[: stmt.rfind(delimiter)]
            if stmt:
                statements.append(stmt)
            current = []

    remainder = "\n".join(current).strip()
    if remainder:
        statements.append(remainder)

    return statements


def main():
    sql_path = os.path.realpath(SQL_FILE)
    if not os.path.exists(sql_path):
        print(f"Arquivo SQL não encontrado: {sql_path}")
        sys.exit(1)

    print(f"Lendo {sql_path}")
    with open(sql_path, encoding="utf-8") as f:
        sql_text = f.read()

    conn = pymysql.connect(
        host=RDS_HOST,
        port=RDS_PORT,
        user=RDS_USER,
        password=RDS_PASSWORD,
        autocommit=True,
        charset="utf8mb4",
    )

    print(f"Conectado ao RDS {RDS_HOST}:{RDS_PORT}")

    statements = split_statements(sql_text)
    executed = 0
    skipped = 0

    with conn.cursor() as cur:
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                skipped += 1
                continue
            try:
                cur.execute(stmt)
                executed += 1
            except pymysql.err.ProgrammingError as e:
                print(f"[WARN] {e} | stmt: {stmt[:80]}")

    conn.close()
    print(f"Concluído: {executed} statements executados, {skipped} ignorados.")


if __name__ == "__main__":
    main()
