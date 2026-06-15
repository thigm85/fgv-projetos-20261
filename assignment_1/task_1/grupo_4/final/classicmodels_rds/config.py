"""Environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# classicmodels_rds/ -> aluno_luciano/ -> grupo_4/ -> task_1/
_TASK1_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_SQL = _TASK1_ROOT / "data" / "mysqlsampledatabase.sql"

_ALUNO_ROOT = Path(__file__).resolve().parent.parent
_CONNECTION_LOCAL = _ALUNO_ROOT / "connection.local.env"


@dataclass(frozen=True)
class Settings:
    aws_region: str
    rds_db_instance_identifier: str
    rds_db_instance_class: str
    rds_engine: str
    rds_engine_version: str
    rds_allocated_storage: int
    rds_master_username: str
    rds_master_password: str
    rds_db_name: str
    rds_port: int
    rds_publicly_accessible: bool
    rds_multi_az: bool
    rds_backup_retention_period: int
    rds_skip_final_snapshot: bool
    rds_final_snapshot_identifier: str
    ec2_security_group_name: str
    sql_file_path: Path
    db_host: str
    db_user: str
    db_password: str
    db_port: int
    db_name: str
    mysql_connect_retries: int
    mysql_connect_delay_seconds: int


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def load_settings() -> Settings:
    """Load `.env` then `connection.local.env` (override) from the aluno_luciano folder."""
    load_dotenv(_ALUNO_ROOT / ".env")
    if _CONNECTION_LOCAL.is_file():
        load_dotenv(_CONNECTION_LOCAL, override=True)

    sql_raw = os.getenv("SQL_FILE_PATH", str(_DEFAULT_SQL))
    sql_path = Path(sql_raw).expanduser()
    if not sql_path.is_absolute():
        sql_path = (_ALUNO_ROOT / sql_path).resolve()

    master_password = os.getenv("RDS_MASTER_PASSWORD", "")
    # Treat empty DB_PASSWORD in .env as "use master password"
    db_password = os.getenv("DB_PASSWORD") or master_password

    return Settings(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        rds_db_instance_identifier=os.getenv(
            "RDS_DB_INSTANCE_IDENTIFIER", "classicmodels-mysql-g4"
        ),
        rds_db_instance_class=os.getenv("RDS_DB_INSTANCE_CLASS", "db.t3.micro"),
        rds_engine=os.getenv("RDS_ENGINE", "mysql"),
        rds_engine_version=os.getenv("RDS_ENGINE_VERSION", "8.0.40"),
        rds_allocated_storage=_i("RDS_ALLOCATED_STORAGE", 20),
        rds_master_username=os.getenv("RDS_MASTER_USERNAME", "admin"),
        rds_master_password=master_password,
        rds_db_name=os.getenv("RDS_DB_NAME", "classicmodels"),
        rds_port=_i("RDS_PORT", 3306),
        rds_publicly_accessible=_b("RDS_PUBLICLY_ACCESSIBLE", "true"),
        rds_multi_az=_b("RDS_MULTI_AZ", "false"),
        rds_backup_retention_period=_i("RDS_BACKUP_RETENTION_PERIOD", 0),
        rds_skip_final_snapshot=_b("RDS_SKIP_FINAL_SNAPSHOT", "true"),
        rds_final_snapshot_identifier=os.getenv("RDS_FINAL_SNAPSHOT_IDENTIFIER", ""),
        ec2_security_group_name=os.getenv(
            "EC2_SECURITY_GROUP_NAME", "classicmodels-rds-mysql-sg"
        ),
        sql_file_path=sql_path,
        db_host=os.getenv("DB_HOST", "").strip(),
        db_user=os.getenv("DB_USER", os.getenv("RDS_MASTER_USERNAME", "admin")),
        db_password=db_password,
        db_port=_i("DB_PORT", 3306),
        db_name=os.getenv("DB_NAME", "classicmodels"),
        mysql_connect_retries=_i("MYSQL_CONNECT_RETRIES", 8),
        mysql_connect_delay_seconds=_i("MYSQL_CONNECT_DELAY_SECONDS", 15),
    )


def write_connection_local_env(*, endpoint: str) -> None:
    """Persist RDS endpoint for load/validate scripts (file is gitignored)."""
    lines = [
        "# Written by scripts/01_provision_rds.py — do not commit",
        f"DB_HOST={endpoint}",
        f"RDS_ENDPOINT={endpoint}",
        "",
    ]
    _CONNECTION_LOCAL.write_text("\n".join(lines), encoding="utf-8")
