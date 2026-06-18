import boto3

rds = boto3.client('rds', region_name='us-east-1')

rds.delete_db_instance(
    DBInstanceIdentifier='db-classicmodels',
    SkipFinalSnapshot=True
)

print("Instância deletada")
