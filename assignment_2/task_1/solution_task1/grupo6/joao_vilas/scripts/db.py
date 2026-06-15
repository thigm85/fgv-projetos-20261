import logging
import time

import pymysql
from pymysql.constants import CLIENT

from config import Settings


logger = logging.getLogger(__name__)


def connect_mysql(settings: Settings, *, multi_statements: bool = False):
    """Conecta ao MySQL com retry exponencial-fixo e seleciona o banco de trabalho.

    O retry existe porque, logo após o `terraform apply`, o RDS pode levar alguns
    segundos para aceitar conexões. Mantém o mesmo contrato do Assignment 1.
    """

    client_flag = CLIENT.MULTI_STATEMENTS if multi_statements else 0
    last_error = None

    for attempt in range(1, settings.connect_retries + 1):
        try:
            logger.info(
                "Conectando ao MySQL %s:%s (tentativa %s/%s)",
                settings.db_host,
                settings.db_port,
                attempt,
                settings.connect_retries,
            )

            return pymysql.connect(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                database=settings.db_name,
                charset="utf8mb4",
                client_flag=client_flag,
                cursorclass=pymysql.cursors.DictCursor,
            )

        except pymysql.MySQLError as exc:
            last_error = exc
            logger.warning("Conexão falhou: %s", exc)

            if attempt < settings.connect_retries:
                time.sleep(settings.connect_delay_seconds)

    raise RuntimeError(f"Não foi possível conectar ao MySQL: {last_error}")
