import boto3

rds = boto3.client('rds', region_name='us-east-1')

response = rds.create_db_instance(
    DBInstanceIdentifier='db-classicmodels',
    AllocatedStorage=20,
    DBInstanceClass='db.t3.micro',
    Engine='mysql',
    MasterUsername='admin',
    MasterUserPassword='senhatop123',
    PubliclyAccessible=True
)

print("Instância criada")
