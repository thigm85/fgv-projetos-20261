import argparse
import logging
import sys

from config import Settings, load_settings
from db import connect_mysql


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table_name,),
    )
    return int(cursor.fetchone()["total"]) > 0


def run_validation(settings: Settings, expect_pending: bool) -> int:
    conn = None
    failures: list[str] = []

    try:
        conn = connect_mysql(settings)

        with conn.cursor() as cursor:
            # 1. tabela e registro do pipeline
            if not table_exists(cursor, "etl_watermark"):
                failures.append("Tabela etl_watermark não existe (rode init_watermark).")
                _report(failures)
                return 1

            cursor.execute(
                """
                SELECT last_processed_order_date, last_run_status
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (settings.pipeline_name,),
            )
            wm = cursor.fetchone()

            if not wm:
                failures.append(
                    f"Registro '{settings.pipeline_name}' ausente em etl_watermark."
                )
                _report(failures)
                return 1

            logger.info("OK: registro '%s' encontrado em etl_watermark", settings.pipeline_name)
            watermark_date = wm["last_processed_order_date"]

            # 2. watermark inicializado
            if watermark_date is None:
                failures.append("last_processed_order_date está NULL (não inicializado).")
            else:
                logger.info("OK: last_processed_order_date = %s", watermark_date)

            # MAX(orderDate) atual
            cursor.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
            max_order_date = cursor.fetchone()["max_order_date"]
            logger.info("MAX(orders.orderDate) = %s", max_order_date)

            has_pending = (
                watermark_date is not None
                and max_order_date is not None
                and max_order_date > watermark_date
            )

            # 3. integridade dos pedidos pendentes
            if watermark_date is not None:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM orders o
                    LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
                    WHERE o.orderDate > %s AND od.orderNumber IS NULL
                    """,
                    (watermark_date,),
                )
                orphan_orders = int(cursor.fetchone()["total"])
                if orphan_orders != 0:
                    failures.append(
                        f"{orphan_orders} pedido(s) pendente(s) sem linhas em orderdetails."
                    )
                else:
                    logger.info("OK: todo pedido pendente possui linhas em orderdetails")

            # 4. dados pendentes
            if has_pending:
                logger.info(
                    "Há dados pendentes de ETL: MAX(orderDate) %s > watermark %s",
                    max_order_date,
                    watermark_date,
                )
            else:
                logger.info("Sem dados pendentes de ETL (origem sincronizada com o watermark).")

            if expect_pending and not has_pending:
                failures.append(
                    "--expect-pending exigido, mas MAX(orderDate) não é maior que o watermark."
                )

        if failures:
            _report(failures)
            return 1

        logger.info("Validação concluída com sucesso — origem pronta para o ETL incremental.")
        return 0

    except Exception:
        logger.exception("Erro fatal na validação")
        return 1

    finally:
        if conn and conn.open:
            conn.close()
            logger.info("Conexão encerrada")


def _report(failures: list[str]) -> None:
    logger.error("Validação falhou com %s erro(s):", len(failures))
    for failure in failures:
        logger.error("- %s", failure)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida a prontidão da origem OLTP para o ETL incremental"
    )
    parser.add_argument(
        "--expect-pending",
        action="store_true",
        help="Falha se NÃO houver pedidos novos acima do watermark (usar após a simulação).",
    )
    args = parser.parse_args()

    settings = load_settings()
    return run_validation(settings, expect_pending=args.expect_pending)


if __name__ == "__main__":
    sys.exit(main())
