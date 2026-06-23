"""Create security group + MySQL RDS; write endpoint to connection.local.env."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classicmodels_rds.aws_provision import (  
    allocate_mysql_rds,
    create_security_group_mysql,
    get_clients,
)
from classicmodels_rds.config import load_settings, write_connection_local_env 


def main() -> None:
    settings = load_settings()
    if not settings.rds_master_password:
        print("Set RDS_MASTER_PASSWORD in .env before provisioning.", file=sys.stderr)
        sys.exit(1)

    rds, ec2 = get_clients(settings.aws_region)
    sg_id = create_security_group_mysql(ec2, settings)
    endpoint = allocate_mysql_rds(rds, sg_id, settings)
    write_connection_local_env(endpoint=endpoint)
    print(f"\nWrote {ROOT / 'connection.local.env'}")
    print("Next: python scripts/02_load_classicmodels.py")


if __name__ == "__main__":
    main()
