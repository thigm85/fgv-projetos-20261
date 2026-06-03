import argparse
import logging
import os
import time
from dataclasses import dataclass

import mysql.connector


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    connect_retries: int
    connect_retry_delay: float


def env_any(names, default=None, required=False):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and default is None:
        raise RuntimeError(f"Missing required environment variable: {', '.join(names)}")
    return default


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=env_any(["CLASSICMODELS_DB_HOST", "DB_HOST", "MYSQL_HOST"]))
    parser.add_argument("--port", type=int, default=int(env_any(["CLASSICMODELS_DB_PORT", "DB_PORT", "MYSQL_PORT"], "3306")))
    parser.add_argument("--user", default=env_any(["CLASSICMODELS_DB_USER", "DB_USER", "MYSQL_USER"]))
    parser.add_argument("--password", default=env_any(["CLASSICMODELS_DB_PASSWORD", "DB_PASSWORD", "MYSQL_PASSWORD"]))
    parser.add_argument("--database", default=env_any(["CLASSICMODELS_DB_NAME", "DB_NAME", "MYSQL_DATABASE"], "classicmodels"))
    parser.add_argument("--connect-retries", type=int, default=int(env_any(["CLASSICMODELS_DB_CONNECT_RETRIES"], "3")))
    parser.add_argument("--connect-retry-delay", type=float, default=float(env_any(["CLASSICMODELS_DB_CONNECT_RETRY_DELAY"], "2")))
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")


def config_from_args(args: argparse.Namespace) -> DbConfig:
    missing = [
        name
        for name, value in {
            "--host or CLASSICMODELS_DB_HOST": args.host,
            "--user or CLASSICMODELS_DB_USER": args.user,
            "--password or CLASSICMODELS_DB_PASSWORD": args.password,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing database configuration: " + ", ".join(missing))

    return DbConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        connect_retries=args.connect_retries,
        connect_retry_delay=args.connect_retry_delay,
    )


def redacted_connection_label(config: DbConfig) -> str:
    return f"{config.user}@{config.host}:{config.port}/{config.database}"


def connect(config: DbConfig):
    logger = logging.getLogger(__name__)
    attempts = max(config.connect_retries, 1)

    for attempt in range(1, attempts + 1):
        try:
            logger.info("Connecting to MySQL (%s), attempt %s/%s", redacted_connection_label(config), attempt, attempts)
            return mysql.connector.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                database=config.database,
                autocommit=False,
            )
        except mysql.connector.Error:
            if attempt == attempts:
                logger.exception("MySQL connection failed after %s attempt(s)", attempts)
                raise
            logger.warning("MySQL connection failed; retrying in %.1f second(s)", config.connect_retry_delay)
            time.sleep(config.connect_retry_delay)
