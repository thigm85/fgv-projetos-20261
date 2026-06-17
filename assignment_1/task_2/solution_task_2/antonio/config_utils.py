from __future__ import annotations

import configparser
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
ENV_FILE = CONFIG_DIR / ".env"


def load_env_config() -> configparser.ConfigParser:
    if not ENV_FILE.exists():
        raise FileNotFoundError(
            f"Missing {ENV_FILE}. Copy config/.env.example to config/.env and fill it."
        )
    parser = configparser.ConfigParser()
    parser.read(ENV_FILE, encoding="utf-8")
    return parser


def section(config: configparser.ConfigParser, name: str) -> dict[str, str]:
    if not config.has_section(name):
        raise KeyError(f"Missing [{name}] section in {ENV_FILE}")
    return {key: value for key, value in config[name].items()}


def configure_aws_env(config: configparser.ConfigParser) -> None:
    aws = section(config, "default")
    mapping = {
        "aws_access_key_id": "AWS_ACCESS_KEY_ID",
        "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY",
        "aws_session_token": "AWS_SESSION_TOKEN",
        "region": "AWS_DEFAULT_REGION",
    }
    for source, target in mapping.items():
        value = aws.get(source)
        if value:
            os.environ[target] = value
    if aws.get("region"):
        os.environ["AWS_REGION"] = aws["region"]

