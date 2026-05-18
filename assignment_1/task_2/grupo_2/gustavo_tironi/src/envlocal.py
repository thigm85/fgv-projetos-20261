import os
from pathlib import Path


def load() -> None:
    """Lê src/.env e preenche os.environ."""
    path = Path(__file__).resolve().parent / ".env"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, val)
