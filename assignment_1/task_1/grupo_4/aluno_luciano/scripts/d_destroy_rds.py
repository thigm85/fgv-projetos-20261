"""Delete RDS instance and security group."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classicmodels_rds.aws_provision import destroy_mysql_rds, get_clients
from classicmodels_rds.config import load_settings


def main() -> None:
    settings = load_settings()
    rds, ec2 = get_clients(settings.aws_region)
    destroy_mysql_rds(rds, ec2, settings)
    local = ROOT / "connection.local.env"
    if local.is_file():
        local.unlink()
        print(f"Removed {local}")


if __name__ == "__main__":
    main()
