"""
Script para provisionar uma instância MySQL no Amazon RDS.
Cria a instância, configura o security group para acesso público e aguarda disponibilidade.
"""

import sys
import time
import boto3
from botocore.exceptions import ClientError
from config import (
    RDS_INSTANCE_IDENTIFIER,
    RDS_DB_NAME,
    RDS_MASTER_USERNAME,
    RDS_MASTER_PASSWORD,
    RDS_INSTANCE_CLASS,
    RDS_ENGINE,
    RDS_ENGINE_VERSION,
    RDS_ALLOCATED_STORAGE,
    RDS_REGION,
    RDS_PORT,
)


def get_or_create_security_group(ec2_client):
    """Cria ou obtém um security group que permite acesso MySQL externo."""
    sg_name = "classicmodels-rds-sg"
    try:
        response = ec2_client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [sg_name]}]
        )
        if response["SecurityGroups"]:
            sg_id = response["SecurityGroups"][0]["GroupId"]
            print(f"Security group já existe: {sg_id}")
            return sg_id
    except ClientError:
        pass

    # Obter VPC padrão
    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    response = ec2_client.create_security_group(
        GroupName=sg_name,
        Description="Security group para acesso ao RDS MySQL classicmodels",
        VpcId=vpc_id,
    )
    sg_id = response["GroupId"]

    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": RDS_PORT,
                "ToPort": RDS_PORT,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "MySQL access"}],
            }
        ],
    )
    print(f"Security group criado: {sg_id}")
    return sg_id


def provision_rds():
    """Provisiona a instância MySQL no RDS."""
    session = boto3.Session(region_name=RDS_REGION)
    rds_client = session.client("rds")
    ec2_client = session.client("ec2")

    # Verificar se a instância já existe
    try:
        response = rds_client.describe_db_instances(
            DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER
        )
        status = response["DBInstances"][0]["DBInstanceStatus"]
        endpoint = response["DBInstances"][0].get("Endpoint", {}).get("Address", "aguardando...")
        print(f"Instância '{RDS_INSTANCE_IDENTIFIER}' já existe. Status: {status}")
        print(f"Endpoint: {endpoint}")
        if status != "available":
            print("Aguardando a instância ficar disponível...")
            wait_for_rds(rds_client)
        return
    except ClientError as e:
        if "DBInstanceNotFound" not in str(e):
            raise

    sg_id = get_or_create_security_group(ec2_client)

    print(f"Criando instância RDS '{RDS_INSTANCE_IDENTIFIER}'...")
    rds_client.create_db_instance(
        DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER,
        DBInstanceClass=RDS_INSTANCE_CLASS,
        Engine=RDS_ENGINE,
        EngineVersion=RDS_ENGINE_VERSION,
        MasterUsername=RDS_MASTER_USERNAME,
        MasterUserPassword=RDS_MASTER_PASSWORD,
        AllocatedStorage=RDS_ALLOCATED_STORAGE,
        VpcSecurityGroupIds=[sg_id],
        PubliclyAccessible=True,
        Port=RDS_PORT,
        BackupRetentionPeriod=0,
        MultiAZ=False,
        StorageType="gp2",
        Tags=[
            {"Key": "Project", "Value": "classicmodels-pipeline"},
            {"Key": "Environment", "Value": "lab"},
        ],
    )
    print("Instância em criação. Aguardando ficar disponível (pode levar alguns minutos)...")
    wait_for_rds(rds_client)


def wait_for_rds(rds_client):
    """Aguarda a instância RDS ficar disponível."""
    waiter = rds_client.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER,
        WaiterConfig={"Delay": 30, "MaxAttempts": 40},
    )
    response = rds_client.describe_db_instances(
        DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER
    )
    endpoint = response["DBInstances"][0]["Endpoint"]["Address"]
    port = response["DBInstances"][0]["Endpoint"]["Port"]
    print(f"\nInstância disponível!")
    print(f"  Endpoint: {endpoint}")
    print(f"  Port: {port}")
    print(f"  Username: {RDS_MASTER_USERNAME}")
    print(f"  Database: {RDS_DB_NAME}")
    print(f"\nGuarde essas informações para os próximos passos.")


if __name__ == "__main__":
    provision_rds()
