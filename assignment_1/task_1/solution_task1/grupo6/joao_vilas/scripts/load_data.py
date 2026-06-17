import argparse
import logging
import sys
import time

import pymysql
from pymysql.constants import CLIENT

from config import Settings, load_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def connect_mysql(settings: Settings):
    last_error = None

    for attempt in range(1, settings.connect_retries + 1):
        try:
            logger.info(
                "Tentando conectar ao MySQL: tentativa %s/%s",
                attempt,
                settings.connect_retries,
            )

            return pymysql.connect(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                client_flag=CLIENT.MULTI_STATEMENTS,
                charset="utf8mb4",
            )

        except pymysql.MySQLError as exc:
            last_error = exc
            logger.warning("Conexão falhou: %s", exc)

            if attempt < settings.connect_retries:
                time.sleep(settings.connect_delay_seconds)

    raise RuntimeError(f"Não foi possível conectar ao MySQL: {last_error}")


def run_load(settings: Settings, dry_run: bool = False) -> int:
    logger.info("Iniciando carga do banco classicmodels")

    if not settings.sql_path.exists():
        logger.error("Arquivo SQL não encontrado: %s", settings.sql_path)
        return 1

    logger.info("Arquivo SQL localizado: %s", settings.sql_path)

    if dry_run:
        logger.info("DRY-RUN: conexão e execução do SQL não serão realizadas")
        logger.info("DRY-RUN: host=%s port=%s user=%s", settings.db_host, settings.db_port, settings.db_user)
        return 0

    conn = None

    try:
        sql_text = settings.sql_path.read_text(encoding="utf-8")
        conn = connect_mysql(settings)
        conn.autocommit(False)

        with conn.cursor() as cursor:
            logger.info("Executando script SQL")
            cursor.execute(sql_text)

            while cursor.nextset():
                pass

        conn.commit()
        logger.info("Carga concluída com sucesso")
        return 0

    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Falha na carga. Rollback executado quando aplicável.")
        return 1

    finally:
        if conn and conn.open:
            conn.close()
            logger.info("Conexão encerrada")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega o banco classicmodels no MySQL RDS")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem executar a carga")
    args = parser.parse_args()

    try:
        settings = load_settings()
        return run_load(settings, dry_run=args.dry_run)
    except Exception:
        logger.exception("Erro fatal na carga")
        return 1


if __name__ == "__main__":
    sys.exit(main())