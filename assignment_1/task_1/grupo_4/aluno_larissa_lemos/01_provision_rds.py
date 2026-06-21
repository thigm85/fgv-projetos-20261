from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from lib_aws import rds_client


def _as_bool(s: str) -> bool:
    v = s.strip().lower()
    if v in {"1", "true", "t", "yes", "y"}:
        return True
    if v in {"0", "false", "f", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("expected a boolean (true/false)")


def _csv(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _get_endpoint(db: dict) -> Optional[dict]:
    ep = db.get("Endpoint") or {}
    if ep.get("Address") and ep.get("Port"):
        return {"host": ep["Address"], "port": ep["Port"]}
    return None


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Provisiona uma instância MySQL no Amazon RDS.")
    p.add_argument("--db-instance-identifier", required=True)
    p.add_argument("--master-username", required=True)
    p.add_argument("--master-password", required=True)
    p.add_argument("--db-instance-class", default="db.t3.micro")
    p.add_argument("--allocated-storage", type=int, default=20)
    p.add_argument("--engine", default="mysql")
    p.add_argument("--engine-version", default=None)
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--publicly-accessible", type=_as_bool, default="true")
    p.add_argument("--vpc-security-group-ids", type=_csv, default=[])
    p.add_argument("--db-subnet-group-name", default=None)
    p.add_argument("--multi-az", type=_as_bool, default="false")
    p.add_argument("--storage-type", default="gp2")
    p.add_argument("--backup-retention-period", type=int, default=0)
    p.add_argument("--wait", type=_as_bool, default="true", help="Aguarda ficar available e imprime endpoint")
    p.add_argument("--region", default=None)
    p.add_argument("--profile", default=None)
    args = p.parse_args(argv)

    rds = rds_client(region=args.region, profile=args.profile)

    create_kwargs = {
        "DBInstanceIdentifier": args.db_instance_identifier,
        "AllocatedStorage": args.allocated_storage,
        "DBInstanceClass": args.db_instance_class,
        "Engine": args.engine,
        "MasterUsername": args.master_username,
        "MasterUserPassword": args.master_password,
        "Port": args.port,
        "PubliclyAccessible": bool(args.publicly_accessible),
        "MultiAZ": bool(args.multi_az),
        "StorageType": args.storage_type,
        "BackupRetentionPeriod": args.backup_retention_period,
    }
    if args.engine_version:
        create_kwargs["EngineVersion"] = args.engine_version
    if args.vpc_security_group_ids:
        create_kwargs["VpcSecurityGroupIds"] = args.vpc_security_group_ids
    if args.db_subnet_group_name:
        create_kwargs["DBSubnetGroupName"] = args.db_subnet_group_name

    try:
        resp = rds.create_db_instance(**create_kwargs)
    except rds.exceptions.DBInstanceAlreadyExistsFault:
        resp = rds.describe_db_instances(DBInstanceIdentifier=args.db_instance_identifier)

    if isinstance(resp.get("DBInstance"), dict):
        db = resp["DBInstance"]
    else:
        dbs = resp.get("DBInstances") or []
        db = dbs[0] if dbs else None
    if not db:
        print("Falha ao obter metadata da instância.", file=sys.stderr)
        return 2

    print(json.dumps({"db_instance_identifier": args.db_instance_identifier, "status": db.get("DBInstanceStatus")}))

    if args.wait:
        waiter = rds.get_waiter("db_instance_available")
        waiter.wait(DBInstanceIdentifier=args.db_instance_identifier)
        db = rds.describe_db_instances(DBInstanceIdentifier=args.db_instance_identifier)["DBInstances"][0]
        endpoint = _get_endpoint(db)
        out = {
            "db_instance_identifier": args.db_instance_identifier,
            "status": db.get("DBInstanceStatus"),
            "endpoint": endpoint,
            "master_username": args.master_username,
        }
        print(json.dumps(out, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

