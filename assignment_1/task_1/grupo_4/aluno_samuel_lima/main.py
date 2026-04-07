import boto3
import time
import mysql.connector
from config import *
import os
from dotenv import load_dotenv

load_dotenv()

# AWS CLIENTS 
region = os.getenv("AWS_REGION", "us-east-1")

print("ACCESS KEY:", os.getenv("AWS_ACCESS_KEY_ID"))
print("REGION:", region)

# rds = boto3.client("rds", region_name=region)
# ec2 = boto3.client("ec2", region_name=region)
rds = boto3.client(
    "rds",
    region_name=region,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
)

ec2 = boto3.client(
    "ec2",
    region_name=region,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
)

# CREATE SECURITY GROUP 
def create_sg():
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    sg = ec2.create_security_group(
        GroupName="classicmodels-sg-samuel-cl",
        Description="MySQL access",
        VpcId=vpc_id,
    )

    sg_id = sg["GroupId"]

    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 3306,
            "ToPort": 3306,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    return sg_id


# CREATE RDS
def create_rds(sg_id):
    rds.create_db_instance(
        DBInstanceIdentifier=RDS_IDENTIFIER,
        DBInstanceClass="db.t3.micro",
        Engine="mysql",
        MasterUsername=DB_USER,
        MasterUserPassword=DB_PASSWORD,
        AllocatedStorage=20,
        VpcSecurityGroupIds=[sg_id],
        PubliclyAccessible=True,
    )

    print("Waiting RDS...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(DBInstanceIdentifier=RDS_IDENTIFIER)

    db = rds.describe_db_instances(DBInstanceIdentifier=RDS_IDENTIFIER)
    endpoint = db["DBInstances"][0]["Endpoint"]["Address"]

    return endpoint


# LOAD SQL 
def load_sql(endpoint):
    conn = mysql.connector.connect(
        host=endpoint,
        user=DB_USER,
        password=DB_PASSWORD,
        use_pure=True 
    )

    cursor = conn.cursor()

    # criar database e usar
    cursor.execute("CREATE DATABASE IF NOT EXISTS classicmodels")
    cursor.execute("USE classicmodels")

    with open("../../data/mysqlsampledatabase.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    print("Executando SQL...")

    for result in conn.cmd_query_iter(sql):
        pass

    print("SQL executado com sucesso!")

    conn.close()


# VALIDATE
def validate(endpoint):
    conn = mysql.connector.connect(
        host=endpoint,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        use_pure=True
    )

    cursor = conn.cursor()

    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    print("Tabelas:", tables)

    conn.close()


if __name__ == "__main__":
    sg_id = create_sg()
    endpoint = create_rds(sg_id)

    load_sql(endpoint)
    validate(endpoint)

    print("Pipeline finalizado!")
