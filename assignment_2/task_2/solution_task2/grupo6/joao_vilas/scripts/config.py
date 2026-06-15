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


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    pipeline_name: str
    aws_region: str
    sql_path: Path
    watermark_sql_path: Path
    connect_retries: int
    connect_delay_seconds: int


def load_settings() -> Settings:
    return Settings(
        db_host=required_env("DB_HOST"),
        db_port=int(os.getenv("DB_PORT", "3306")),
        db_user=os.getenv("DB_USER", "admin"),
        db_password=required_env("DB_PASSWORD"),
        db_name=os.getenv("DB_NAME", "classicmodels"),
        pipeline_name=os.getenv("PIPELINE_NAME", "classicmodels_sales"),
        aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
        sql_path=_resolve(os.getenv("MYSQL_SQL_PATH", "data/mysqlsampledatabase.sql")),
        watermark_sql_path=_resolve(
            os.getenv("WATERMARK_SQL_PATH", "sql/init_watermark.sql")
        ),
        connect_retries=int(os.getenv("MYSQL_CONNECT_RETRIES", "10")),
        connect_delay_seconds=int(os.getenv("MYSQL_CONNECT_DELAY_SECONDS", "10")),
    )
