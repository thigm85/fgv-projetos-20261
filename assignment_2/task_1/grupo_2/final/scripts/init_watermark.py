#!/usr/bin/env python3
"""
Inicializa a tabela etl_watermark no banco classicmodels.

Idempotente — pode ser executado múltiplas vezes com segurança:
  1. Cria a tabela se não existir.
  2. Insere o registro 'classicmodels_sales' se ausente.
  3. Inicializa last_processed_order_date com MAX(orders.orderDate) atual.
  4. Se o registro já existir com watermark preenchido, NÃO sobrescreve
     (preserva progresso real de execuções anteriores do ETL).

Fontes de design:
  - Estrutura e logging: Matheus Carvalho
  - UPSERT inteligente com preservação de progresso: Alessandra Bello

Exit code: 0 = sucesso, 1 = falha.
"""

import logging
import sys
from pathlib import Path

# Adiciona o diretório pai ao path para importar db_config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db_config

PIPELINE_NAME = "classicmodels_sales"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("init_watermark")

# ── SQL Statements ───────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name             VARCHAR(64)  NOT NULL,
    last_processed_order_date DATE         NULL,
    last_run_at               DATETIME     NULL,
    last_run_status           VARCHAR(32)  NOT NULL DEFAULT 'NEVER_RUN',
    PRIMARY KEY (pipeline_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# UPSERT inteligente (Alessandra):
#   - Se o registro não existir: insere com MAX(orderDate) como watermark.
#   - Se existir mas last_processed_order_date for NULL: atualiza com MAX(orderDate).
#   - Se existir com watermark já preenchido: NÃO sobrescreve (preserva progresso real).
UPSERT_SQL = """
INSERT INTO etl_watermark
    (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
VALUES
    (%(pipeline_name)s, %(max_date)s, NULL, 'NEVER_RUN')
ON DUPLICATE KEY UPDATE
    last_processed_order_date = CASE
        WHEN last_processed_order_date IS NULL THEN VALUES(last_processed_order_date)
        ELSE last_processed_order_date
    END
"""


def main() -> int:
    conn = None
    try:
        conn = db_config.get_connection(autocommit=False)
        cur = conn.cursor()

        # 1. Cria tabela
        log.info("Criando tabela etl_watermark (se não existir)...")
        cur.execute(CREATE_TABLE_SQL)

        # 2. Obtém MAX(orderDate) como baseline
        cur.execute("SELECT MAX(orderDate) FROM orders")
        max_date = cur.fetchone()[0]

        if max_date is None:
            log.error("Tabela 'orders' está vazia ou não existe. Verifique a carga do A1.")
            return 1

        log.info("MAX(orders.orderDate) encontrado: %s", max_date)

        # 3. UPSERT do registro
        log.info("Inserindo/validando registro '%s'...", PIPELINE_NAME)
        cur.execute(UPSERT_SQL, {"pipeline_name": PIPELINE_NAME, "max_date": max_date})
        affected = cur.rowcount

        conn.commit()

        # 4. Mostra estado final
        cur.execute(
            "SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status "
            "FROM etl_watermark WHERE pipeline_name = %s",
            (PIPELINE_NAME,),
        )
        row = cur.fetchone()
        cur.close()

        if row is None:
            log.error("Registro '%s' não encontrado após upsert — algo deu errado.", PIPELINE_NAME)
            return 1

        pipeline, wm_date, run_at, status = row

        if affected == 1:
            log.info("✓ Registro CRIADO:")
        elif affected == 2:
            log.info("✓ Registro atualizado (watermark estava NULL):")
        else:
            log.info("✓ Registro já existia com watermark preenchido (sem alteração):")

        log.info("  pipeline_name             = %s", pipeline)
        log.info("  last_processed_order_date  = %s", wm_date)
        log.info("  last_run_at               = %s", run_at)
        log.info("  last_run_status           = %s", status)

        return 0

    except Exception as exc:
        log.exception("Falha ao inicializar watermark: %s", exc)
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
