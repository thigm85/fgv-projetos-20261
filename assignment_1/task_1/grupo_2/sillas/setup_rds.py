import boto3
import time
from pathlib import Path
import mysql.connector

# Configurações
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR.parent.parent / 'data'
AWS_REGION = "us-east-1"

DB_IDENTIFIER = "classicmodels-db-instance"

DB_NAME = "classicmodels"
DB_USER = "admin"
DB_PASSWORD = "euadoroaemap123" 
DB_PORT = 3306

rds = boto3.client('rds', region_name=AWS_REGION)
ec2 = boto3.client('ec2', region_name=AWS_REGION)

def setup_security_group():
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    vpc_id = vpcs['Vpcs'][0]['VpcId']
    
    try:
        sg = ec2.create_security_group(
            GroupName='classicmodels-db-sg',
            Description='Task 1 MySQL Access',
            VpcId=vpc_id
        )
        sg_id = sg['GroupId']
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': DB_PORT, 'ToPort': DB_PORT, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}]
        )
        return sg_id
    except Exception as e:
        if "InvalidGroup.Duplicate" in str(e):
            sgs = ec2.describe_security_groups(GroupNames=['classicmodels-db-sg'])
            return sgs['SecurityGroups'][0]['GroupId']
        raise e

def create_rds_instance(sg_id):
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=DB_IDENTIFIER,
            AllocatedStorage=20,
            DBInstanceClass='db.t3.micro',
            Engine='mysql',
            EngineVersion='8.0',
            MasterUsername=DB_USER,
            MasterUserPassword=DB_PASSWORD,
            DBName=DB_NAME,
            VpcSecurityGroupIds=[sg_id],
            PubliclyAccessible=True
        )
    except Exception as e:
        if "DBInstanceAlreadyExists" not in str(e):
            raise e

    rds.get_waiter('db_instance_available').wait(DBInstanceIdentifier=DB_IDENTIFIER)
    response = rds.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
    return response['DBInstances'][0]['Endpoint']['Address']

def load_database(endpoint):
    time.sleep(10)
    try:
        conn = mysql.connector.connect(
            host=endpoint, 
            database=DB_NAME, 
            user=DB_USER, 
            password=DB_PASSWORD, 
            port=DB_PORT
        )
        cursor = conn.cursor()
        sql_path = DATA_DIR / 'mysqlsampledatabase.sql'
        
        with open(sql_path, 'r', encoding='utf-8') as f:
            sql_file = f.read()
            sql_commands = sql_file.split(';\n')
            
            for command in sql_commands:
                if command.strip():
                    try:
                        cursor.execute(command)
                    except Exception as e:
                        print(f"Erro ao executar comando: {e}")

        conn.commit()
        return conn, cursor
    except Exception as e:
        print(f"Erro no Load: {e}")
        return None, None

def validate_database(conn, cursor):
    if not cursor:
        return
    try:
        cursor.execute("SHOW TABLES;")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"Tabelas: {', '.join(tables)}")
        
        expected = ['customers', 'products', 'productlines', 'orders', 'orderdetails', 'payments', 'employees', 'offices']
        missing = [t for t in expected if t not in tables]

        for table in expected:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f" - {table}: {count} linhas")
    
    except Exception as e:
        print(f"Erro na validação: {e}")

    finally:
        cursor.close()
        conn.close()

def cleanup():
    try:
        rds.delete_db_instance(DBInstanceIdentifier=DB_IDENTIFIER, SkipFinalSnapshot=True)
        rds.get_waiter('db_instance_deleted').wait(DBInstanceIdentifier=DB_IDENTIFIER)
    except Exception as e:
        print(f"Erro ao excluir instância RDS: {e}")

    try:
        sgs = ec2.describe_security_groups(GroupNames=['classicmodels-db-sg'])
        ec2.delete_security_group(GroupId=sgs['SecurityGroups'][0]['GroupId'])
    except Exception as e:
        print(f"Erro ao excluir security group: {e}")

def main():
    try:
        sg_id = setup_security_group()
        host = create_rds_instance(sg_id)
        conn, cursor = load_database(host)

        if conn:
            validate_database(conn, cursor)
        
        print(f"Host: {host}")

    except Exception as e:
        print(f"Erro: {e}")
    
    # finally:
    #     cleanup()

if __name__ == "__main__":
    main()
    # cleanup()
