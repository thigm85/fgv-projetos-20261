from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Iterable, TypeVar

TASK_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = TASK_ROOT / ".env"
DEFAULT_SQL_FILE = TASK_ROOT / "data" / "mysqlsampledatabase.sql"
REQUIRED_TABLES = (
    "customers",
    "products",
    "productlines",
    "orders",
    "orderdetails",
    "payments",
    "employees",
    "offices",
)

T = TypeVar("T")


class ConfigError(RuntimeError):
    """Raised when a required configuration value is missing or invalid."""


def strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def serialize_env_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_env_file(env_file: Path = DEFAULT_ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue

        key, raw_value = raw_line.split("=", 1)
        key = key.strip()
        value = strip_wrapping_quotes(raw_value.strip())
        values[key] = value
        os.environ.setdefault(key, value)

    return values


def write_env_updates(env_file: Path, updates: dict[str, object]) -> None:
    serialized = {
        key: serialize_env_value(value)
        for key, value in updates.items()
        if value is not None
    }
    env_file.parent.mkdir(parents=True, exist_ok=True)

    existing_lines = (
        env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    )
    updated_lines: list[str] = []
    seen: set[str] = set()

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue

        key, _ = line.split("=", 1)
        key = key.strip()
        if key in serialized:
            updated_lines.append(f"{key}={serialized[key]}")
            seen.add(key)
        else:
            updated_lines.append(line)

    missing_keys = [key for key in serialized if key not in seen]
    if missing_keys and updated_lines and updated_lines[-1].strip():
        updated_lines.append("")

    for key in missing_keys:
        updated_lines.append(f"{key}={serialized[key]}")

    env_file.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def resolve_env_path(raw_path: str | None) -> Path:
    if not raw_path:
        return DEFAULT_ENV_FILE
    return Path(raw_path).expanduser().resolve()


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}.") from exc


def get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean value, got {value!r}.")


def require_env(names: Iterable[str]) -> dict[str, str]:
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise ConfigError(
            "Missing required environment variables: "
            + ", ".join(sorted(missing))
            + "."
        )
    return {name: os.environ[name] for name in names}


def wait_with_backoff(
    operation: Callable[[], T],
    *,
    retries: int,
    delay_seconds: float,
    factor: float = 1.5,
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    description: str,
) -> T:
    last_error: BaseException | None = None
    current_delay = delay_seconds

    for attempt in range(1, retries + 1):
        try:
            return operation()
        except retryable_exceptions as exc:  # type: ignore[misc]
            last_error = exc
            if attempt == retries:
                break
            print(
                f"[retry] {description} failed on attempt {attempt}/{retries}: {exc}. "
                f"Retrying in {current_delay:.1f}s."
            )
            time.sleep(current_delay)
            current_delay *= factor

    if last_error is None:
        raise RuntimeError(f"{description} failed without raising an exception.")
    raise last_error

