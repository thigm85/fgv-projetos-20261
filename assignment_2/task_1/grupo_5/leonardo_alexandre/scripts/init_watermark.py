"""
Cria a tabela etl_watermark e insere o registro inicial classicmodels_sales.
Idempotente: reexecução não altera watermark já existente.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import PIPELINE_NAME
from db import connect

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name VARCHAR(64) NOT NULL,
    last_processed_order_date DATE NULL,
    last_run_at DATETIME NULL,
    last_run_status VARCHAR(32) NOT NULL DEFAULT 'NEVER_RUN',
    PRIMARY KEY (pipeline_name)
)
"""

INSERT_INITIAL_SQL = """
INSERT INTO etl_watermark (
    pipeline_name,
    last_processed_order_date,
    last_run_at,
    last_run_status
)
SELECT %s, (SELECT MAX(orderDate) FROM orders), NULL, 'NEVER_RUN'
WHERE NOT EXISTS (
    SELECT 1 FROM etl_watermark WHERE pipeline_name = %s
)
"""


def main() -> int:
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE_SQL)
        cursor.execute(INSERT_INITIAL_SQL, (PIPELINE_NAME, PIPELINE_NAME))
        conn.commit()

        cursor.execute(
            """
            SELECT last_processed_order_date, last_run_status
            FROM etl_watermark
            WHERE pipeline_name = %s
            """,
            (PIPELINE_NAME,),
        )
        row = cursor.fetchone()
        if not row:
            print(f"ERRO: registro {PIPELINE_NAME!r} não encontrado após inicialização.")
            return 1

        watermark_date, status = row
        print(f"OK: etl_watermark pronta para {PIPELINE_NAME!r}")
        print(f"    last_processed_order_date = {watermark_date}")
        print(f"    last_run_status = {status}")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERRO: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
