import logging
import sys

from config import Settings, load_settings
from db import connect_mysql


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def read_watermark(cursor, pipeline_name: str) -> dict | None:
    cursor.execute(
        """
        SELECT pipeline_name,
               last_processed_order_date,
               last_run_at,
               last_run_status
        FROM etl_watermark
        WHERE pipeline_name = %s
        """,
        (pipeline_name,),
    )
    return cursor.fetchone()


def run_init(settings: Settings) -> int:
    if not settings.sql_path.exists():
        logger.error("SQL de inicialização não encontrado: %s", settings.sql_path)
        return 1

    sql_text = settings.sql_path.read_text(encoding="utf-8")
    conn = None

    try:
        conn = connect_mysql(settings, multi_statements=True)
        conn.autocommit(False)

        with conn.cursor() as cursor:
            logger.info("Aplicando %s", settings.sql_path.name)
            cursor.execute(sql_text)
            while cursor.nextset():
                pass

        conn.commit()

        with conn.cursor() as cursor:
            row = read_watermark(cursor, settings.pipeline_name)

        if not row:
            logger.error(
                "Registro '%s' não encontrado após inicialização", settings.pipeline_name
            )
            return 1

        logger.info("Watermark inicializado:")
        logger.info("  pipeline_name             = %s", row["pipeline_name"])
        logger.info("  last_processed_order_date = %s", row["last_processed_order_date"])
        logger.info("  last_run_at               = %s", row["last_run_at"])
        logger.info("  last_run_status           = %s", row["last_run_status"])

        if row["last_processed_order_date"] is None:
            logger.error(
                "last_processed_order_date está NULL — a tabela orders pode estar vazia. "
                "Carregue o banco classicmodels antes de inicializar o watermark."
            )
            return 1

        logger.info("Inicialização concluída com sucesso")
        return 0

    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Falha ao inicializar o watermark. Rollback executado.")
        return 1

    finally:
        if conn and conn.open:
            conn.close()
            logger.info("Conexão encerrada")


def main() -> int:
    try:
        settings = load_settings()
        return run_init(settings)
    except Exception:
        logger.exception("Erro fatal na inicialização do watermark")
        return 1


if __name__ == "__main__":
    sys.exit(main())
