import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    sql_path: Path
    connect_retries: int
    connect_delay_seconds: int


def load_settings() -> Settings:
    sql_path = Path(os.getenv("MYSQL_SQL_PATH", "data/mysqlsampledatabase.sql"))

    if not sql_path.is_absolute():
        sql_path = PROJECT_ROOT / sql_path

    return Settings(
        db_host=required_env("DB_HOST"),
        db_port=int(os.getenv("DB_PORT", "3306")),
        db_user=os.getenv("DB_USER", "admin"),
        db_password=required_env("DB_PASSWORD"),
        db_name=os.getenv("DB_NAME", "classicmodels"),
        sql_path=sql_path,
        connect_retries=int(os.getenv("MYSQL_CONNECT_RETRIES", "10")),
        connect_delay_seconds=int(os.getenv("MYSQL_CONNECT_DELAY_SECONDS", "10")),
    )