import os
import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv('AWS_REGION')
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID')

rds = boto3.client('rds', region_name=AWS_REGION)
ec2 = boto3.client('ec2', region_name=AWS_REGION)

instancia = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
sg_id = instancia['DBInstances'][0]['VpcSecurityGroups'][0]['VpcSecurityGroupId']

try:
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpProtocol='tcp',
        FromPort=3306,
        ToPort=3306,
        CidrIp='0.0.0.0/0'
    )
    print(f"Porta 3306 liberada no Security Group {sg_id}.")
except Exception as e:
    print(f"Resultado: {e}")
