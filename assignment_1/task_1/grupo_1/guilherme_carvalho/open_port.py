import boto3

rds = boto3.client('rds', region_name='us-east-1')
ec2 = boto3.client('ec2', region_name='us-east-1')

instancia = rds.describe_db_instances(DBInstanceIdentifier='db-classicmodels')
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
