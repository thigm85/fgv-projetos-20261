"""
Script para destruir todos os recursos AWS criados pelo projeto:
- Instância RDS MySQL
- Security group associado
"""

import sys
import boto3
from botocore.exceptions import ClientError
from config import RDS_INSTANCE_IDENTIFIER, RDS_REGION


def destroy_all():
    session = boto3.Session(region_name=RDS_REGION)
    rds_client = session.client("rds")
    ec2_client = session.client("ec2")

    # 1. Deletar instância RDS
    print(f"Deletando instância RDS '{RDS_INSTANCE_IDENTIFIER}'...")
    try:
        rds_client.delete_db_instance(
            DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER,
            SkipFinalSnapshot=True,
            DeleteAutomatedBackups=True,
        )
        print("Instância marcada para deleção. Aguardando...")
        waiter = rds_client.get_waiter("db_instance_deleted")
        waiter.wait(
            DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER,
            WaiterConfig={"Delay": 30, "MaxAttempts": 60},
        )
        print("Instância RDS deletada.")
    except ClientError as e:
        if "DBInstanceNotFound" in str(e):
            print("Instância RDS não encontrada (já deletada).")
        else:
            raise

    # 2. Deletar security group
    sg_name = "classicmodels-rds-sg"
    print(f"Deletando security group '{sg_name}'...")
    try:
        response = ec2_client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [sg_name]}]
        )
        for sg in response["SecurityGroups"]:
            ec2_client.delete_security_group(GroupId=sg["GroupId"])
            print(f"Security group {sg['GroupId']} deletado.")
        if not response["SecurityGroups"]:
            print("Security group não encontrado (já deletado).")
    except ClientError as e:
        print(f"Erro ao deletar security group: {e}")

    print("\nTodos os recursos foram destruídos.")


if __name__ == "__main__":
    confirm = input("Tem certeza que deseja destruir TODOS os recursos AWS do projeto? (sim/nao): ")
    if confirm.strip().lower() == "sim":
        destroy_all()
    else:
        print("Operação cancelada.")
