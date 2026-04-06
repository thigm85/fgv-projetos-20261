"""Create EC2 security group + MySQL RDS instance."""

from __future__ import annotations

import time

import boto3
from botocore.exceptions import ClientError

from classicmodels_rds.config import Settings


def get_clients(region: str) -> tuple:
    session = boto3.Session(region_name=region)
    return session.client("rds"), session.client("ec2")


def create_security_group_mysql(ec2, settings: Settings) -> str:
    """Inbound TCP 3306 on default VPC. Idempotent by group name."""
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        raise RuntimeError("No default VPC found in this region.")
    vpc_id = vpcs["Vpcs"][0]["VpcId"]
    name = settings.ec2_security_group_name
    port = settings.rds_port

    try:
        sg = ec2.create_security_group(
            GroupName=name,
            Description="Task1 classicmodels MySQL RDS inbound",
            VpcId=vpc_id,
        )
        sg_id = sg["GroupId"]
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )
        print(f"[SG]  Created {sg_id}  (VPC {vpc_id}, port {port})")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "InvalidGroup.Duplicate":
            existing = ec2.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": [name]}]
            )
            sg_id = existing["SecurityGroups"][0]["GroupId"]
            print(f"[SG]  Already exists: {sg_id}")
        else:
            raise
    return sg_id


def allocate_mysql_rds(rds, sg_id: str, settings: Settings) -> str:
    """Create instance, wait until available, return endpoint hostname."""
    ident = settings.rds_db_instance_identifier
    print(
        f"[RDS] Creating '{ident}' ({settings.rds_db_instance_class} / "
        f"{settings.rds_engine} {settings.rds_engine_version}) ..."
    )
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=ident,
            DBInstanceClass=settings.rds_db_instance_class,
            Engine=settings.rds_engine,
            EngineVersion=settings.rds_engine_version,
            MasterUsername=settings.rds_master_username,
            MasterUserPassword=settings.rds_master_password,
            DBName=settings.rds_db_name,
            AllocatedStorage=settings.rds_allocated_storage,
            StorageType="gp2",
            VpcSecurityGroupIds=[sg_id],
            PubliclyAccessible=settings.rds_publicly_accessible,
            MultiAZ=settings.rds_multi_az,
            BackupRetentionPeriod=settings.rds_backup_retention_period,
            AutoMinorVersionUpgrade=True,
            Tags=[{"Key": "purpose", "Value": "task1-classicmodels"}],
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "DBInstanceAlreadyExists":
            print("[RDS] Instance already exists; waiting for available state ...")
        else:
            raise

    print("[RDS] Waiting for 'available' (often 5–15 min on first create) ...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=ident,
        WaiterConfig={"Delay": 30, "MaxAttempts": 60},
    )

    info = rds.describe_db_instances(DBInstanceIdentifier=ident)
    inst = info["DBInstances"][0]
    endpoint = inst["Endpoint"]["Address"]
    print(f"[RDS] Ready  endpoint={endpoint}  engine={inst['EngineVersion']}")
    return endpoint


def describe_endpoint(rds, settings: Settings) -> str:
    info = rds.describe_db_instances(
        DBInstanceIdentifier=settings.rds_db_instance_identifier
    )
    return info["DBInstances"][0]["Endpoint"]["Address"]


def destroy_mysql_rds(rds, ec2, settings: Settings) -> None:
    """Delete RDS instance then security group."""
    ident = settings.rds_db_instance_identifier
    print(f"[RDS] Deleting '{ident}' ...")
    try:
        kwargs = {
            "DBInstanceIdentifier": ident,
            "DeleteAutomatedBackups": True,
        }
        if settings.rds_skip_final_snapshot:
            kwargs["SkipFinalSnapshot"] = True
        else:
            kwargs["SkipFinalSnapshot"] = False
            snap_id = settings.rds_final_snapshot_identifier or f"{ident}-final"
            kwargs["FinalDBSnapshotIdentifier"] = snap_id

        rds.delete_db_instance(**kwargs)
        w = rds.get_waiter("db_instance_deleted")
        w.wait(
            DBInstanceIdentifier=ident,
            WaiterConfig={"Delay": 30, "MaxAttempts": 60},
        )
        print("[RDS] Instance deleted.")
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("DBInstanceNotFound", "InvalidDBInstanceState"):
            print("[RDS] Instance not found or already deleted.")
        else:
            raise

    # Brief pause so ENI / SG associations release
    time.sleep(10)

    name = settings.ec2_security_group_name
    try:
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [name]}]
        )
        if sgs["SecurityGroups"]:
            sg_id = sgs["SecurityGroups"][0]["GroupId"]
            ec2.delete_security_group(GroupId=sg_id)
            print(f"[SG]  Deleted {sg_id}")
    except ClientError as exc:
        print(f"[SG]  Could not delete: {exc.response['Error']['Code']}")
