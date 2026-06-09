"""
Task 1 (3.1) — Inicializa a tabela de controle etl_watermark no RDS.

Idempotente:
  1. Cria a tabela etl_watermark se não existir.
  2. Insere o registro pipeline_name='classicmodels_sales' SOMENTE se ausente
     (reexecução não sobrescreve um watermark já avançado pela Task 2).
  3. Inicializa last_processed_order_date com MAX(orders.orderDate) atual.

Uso:
  python init_watermark.py
"""
import sys
from datetime import datetime

from db import load_config, connect_with_retry

PIPELINE_NAME = "classicmodels_sales"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name             VARCHAR(64)  NOT NULL,
    last_processed_order_date DATE,
    last_run_at               DATETIME,
    last_run_status           VARCHAR(32),
    PRIMARY KEY (pipeline_name)
) ENGINE=InnoDB DEFAULT CHARSET=latin1
"""


def init_watermark(conn) -> None:
    with conn.cursor() as cur:
        # 1. Cria a tabela (idempotente)
        print("\nPasso 1/3 — Criando tabela etl_watermark (se não existir)...")
        cur.execute(CREATE_TABLE_SQL)
        print("  Tabela pronta.")

        # 2. Verifica se o registro já existe
        print(f"\nPasso 2/3 — Verificando registro '{PIPELINE_NAME}'...")
        cur.execute(
            "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
            (PIPELINE_NAME,),
        )
        row = cur.fetchone()

        if row is not None:
            print(f"  Registro já existe (last_processed_order_date={row[0]}). "
                  "Nada a alterar (idempotente).")
            return

        # 3. Inicializa com MAX(orderDate)
        print(f"\nPasso 3/3 — Inserindo watermark inicial...")
        cur.execute("SELECT MAX(orderDate) FROM orders")
        max_date = cur.fetchone()[0]
        if max_date is None:
            raise RuntimeError("Nenhum pedido encontrado em 'orders'. Banco vazio?")

        cur.execute(
            "INSERT INTO etl_watermark "
            "(pipeline_name, last_processed_order_date, last_run_at, last_run_status) "
            "VALUES (%s, %s, %s, %s)",
            (PIPELINE_NAME, max_date, datetime.utcnow(), "NEVER_RUN"),
        )
        print(f"  Inserido: pipeline_name={PIPELINE_NAME}, "
              f"last_processed_order_date={max_date}, last_run_status=NEVER_RUN")


def main() -> int:
    print("=" * 60)
    print("Task 1 (3.1) — Inicialização do watermark")
    print("=" * 60)

    cfg = load_config()
    conn = None
    try:
        conn = connect_with_retry(cfg)
        init_watermark(conn)
        conn.commit()
        print("\n  Transação commitada.")

        # Estado final
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status "
                "FROM etl_watermark WHERE pipeline_name = %s",
                (PIPELINE_NAME,),
            )
            print("\nEstado final do watermark:")
            print(f"  {cur.fetchone()}")

    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"\n[ERRO] {exc} — rollback realizado.")
        return 1
    finally:
        if conn:
            conn.close()
            print("\n  Conexão encerrada.")

    print("\n" + "=" * 60)
    print("Inicialização do watermark concluída com sucesso.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
