import boto3

rds = boto3.client("rds")

response = rds.create_db_instance(
    DBName="classicmodels",
    DBInstanceIdentifier="classicmodels-db",
    AllocatedStorage=20,
    DBInstanceClass="db.t3.micro",
    Engine="mysql",
    MasterUsername="admin",
    MasterUserPassword="Admin1234!",
    PubliclyAccessible=True
)

print("Criando RDS...")