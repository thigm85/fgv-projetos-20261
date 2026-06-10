"""Configuração compartilhada dos scripts da Task 1 (Assignment 2)."""

from __future__ import annotations

import os
from pathlib import Path

PIPELINE_NAME = "classicmodels_sales"

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[3]


def env_any(names: list[str], default: str | None = None, required: bool = False) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and not default:
        raise RuntimeError(f"Variável obrigatória ausente: {', '.join(names)}")
    return default or ""


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_env() -> None:
    candidates = [
        ROOT / ".env",
        REPO_ROOT / "assignment_1" / "task_1" / "grupo_5" / "leonardo_alexandre" / ".env",
        REPO_ROOT / "assignment_1" / "task_1" / ".env",
    ]
    for path in candidates:
        _load_env_file(path)


def db_config() -> dict[str, str | int]:
    load_env()
    host = env_any(["DB_HOST", "MYSQL_HOST"], required=True)
    return {
        "host": host,
        "port": int(env_any(["DB_PORT", "MYSQL_PORT"], default="3306")),
        "database": env_any(["DB_NAME", "MYSQL_DATABASE"], default="classicmodels"),
        "user": env_any(["DB_USER", "MYSQL_USER"], required=True),
        "password": env_any(["DB_PASSWORD", "MYSQL_PASSWORD"], required=True),
    }
