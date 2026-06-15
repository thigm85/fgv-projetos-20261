from __future__ import annotations

import argparse
import logging
import sys
import time

import pymysql
from pymysql.constants import CLIENT

from config import AppConfig, DbCredentials, load_config, load_db_credentials


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def connect_mysql(config: AppConfig, creds: DbCredentials):
    last_error: Exception | None = None

    for attempt in range(1, config.connect_retries + 1):
        try:
            logger.info(
                "Conectando ao MySQL: tentativa %s/%s host=%s",
                attempt,
                config.connect_retries,
                creds.host,
            )

            return pymysql.connect(
                host=creds.host,
                port=creds.port,
                user=creds.username,
                password=creds.password,
                client_flag=CLIENT.MULTI_STATEMENTS,
                charset="utf8mb4",
                connect_timeout=15,
            )

        except pymysql.MySQLError as exc:
            last_error = exc
            logger.warning("Conexao falhou: %s", exc)

            if attempt < config.connect_retries:
                time.sleep(config.connect_delay_seconds)

    raise RuntimeError(f"Nao foi possivel conectar ao MySQL: {last_error}")


def run_load(dry_run: bool = False) -> int:
    config = load_config()

    logger.info("Iniciando carga do banco %s", config.sql_path)

    if not config.sql_path.exists():
        logger.error("Arquivo SQL nao encontrado: %s", config.sql_path)
        return 1

    creds = load_db_credentials()

    if dry_run:
        logger.info(
            "DRY-RUN: host=%s port=%s user=%s dbname=%s",
            creds.host,
            creds.port,
            creds.username,
            creds.dbname,
        )
        return 0

    conn = None

    try:
        sql_text = config.sql_path.read_text(encoding="utf-8")
        conn = connect_mysql(config, creds)
        conn.autocommit(False)

        with conn.cursor() as cursor:
            logger.info("Executando script SQL (multistatement)")
            cursor.execute(sql_text)

            while cursor.nextset():
                pass

        conn.commit()
        logger.info("Carga concluida com sucesso")
        return 0

    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Falha na carga. Rollback executado quando aplicavel.")
        return 1

    finally:
        if conn and conn.open:
            conn.close()
            logger.info("Conexao encerrada")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega o banco classicmodels no MySQL RDS")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem executar")
    args = parser.parse_args()

    try:
        return run_load(dry_run=args.dry_run)
    except Exception:
        logger.exception("Erro fatal na carga")
        return 1


if __name__ == "__main__":
    sys.exit(main())
