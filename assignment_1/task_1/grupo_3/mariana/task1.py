import boto3
import pymysql
import requests

REGION = "us-east-1"
DB_ID = "task1-mysql"
USERNAME = "mariana"
PASSWORD = "password123"

ec2 = boto3.client("ec2", region_name=REGION)
rds = boto3.client("rds", region_name=REGION)

ip = requests.get("https://checkip.amazonaws.com").text.strip()

vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
vpc_id = vpcs["Vpcs"][0]["VpcId"]

sg = ec2.create_security_group(
    GroupName="task1-security",
    Description="MySQL access",
    VpcId=vpc_id
)
sg_id = sg["GroupId"]


ec2.authorize_security_group_ingress(
    GroupId=sg_id,
    IpPermissions=[{
        "IpProtocol": "tcp",
        "FromPort": 3306,
        "ToPort": 3306,
        "IpRanges": [{"CidrIp": f"{ip}/32"}]
    }]
)

print("SG criado:", sg_id)

#criar RDS
rds.create_db_instance(
    DBInstanceIdentifier=DB_ID,
    AllocatedStorage=5,
    DBInstanceClass="db.t3.micro",
    Engine="mysql",
    MasterUsername=USERNAME,
    MasterUserPassword=PASSWORD,
    PubliclyAccessible=True,
    VpcSecurityGroupIds=[sg_id],
    BackupRetentionPeriod=0
)

print("Criando RDS...")

# esperar ficar disponível
waiter = rds.get_waiter("db_instance_available")
waiter.wait(DBInstanceIdentifier=DB_ID)

db = rds.describe_db_instances(DBInstanceIdentifier=DB_ID)
endpoint = db["DBInstances"][0]["Endpoint"]["Address"]

print("RDS pronto")
print("HOST:", endpoint)

SQL_FILE = "../../data/mysqlsampledatabase.sql"

with open(SQL_FILE, "r", encoding="utf-8") as f:
    querys = f.read()

    commands = []
    statement = ""
    in_multiline_comment = False

    for line in querys.splitlines():
        line = line.strip()

        # entra em comentário multilinha
        if line.startswith("/*") and not line.startswith("/*!"):
            in_multiline_comment = True
            if "*/" in line:
                in_multiline_comment = False
            continue

        # sai de comentário multilinha
        if in_multiline_comment:
            if "*/" in line:
                in_multiline_comment = False
            continue

        # ignora diretivas tipo /*!40101 ... */
        if line.startswith("/*!"):
            continue

        # ignora comentários simples
        if not line or line.startswith("--"):
            continue

        statement += line + " "

        if line.endswith(";"):
            commands.append(statement.strip())
            statement = ""

    conn = pymysql.connect(
        host=endpoint,
        port=3306,
        user=USERNAME,
        password=PASSWORD,  
        autocommit=True,
        charset="utf8mb4"
    )

    try:
        with conn.cursor() as cursor:
            for i, stmt in enumerate(commands, start=1):
                cursor.execute(stmt)
                print(f"[OK] Comando {i}/{len(commands)}")
    finally:
        conn.close()

    print("Carga concluída.")


# drop das instancias criadas
# DB_ID = "task1-mysql"
# SG_NAME = "task1-security"

# # 1. deletar RDS
# try:
#     rds.delete_db_instance(
#         DBInstanceIdentifier=DB_ID,
#         SkipFinalSnapshot=True,   # importante pra não travar
#         DeleteAutomatedBackups=True
#     )
#     print("Deletando RDS...")
# except Exception as e:
#     print("Erro ao deletar RDS:", e)

# # 2. esperar apagar
# try:
#     waiter = rds.get_waiter("db_instance_deleted")
#     waiter.wait(DBInstanceIdentifier=DB_ID)
#     print("RDS deletado")
# except Exception as e:
#     print("Erro esperando deleção:", e)

# # 3. achar SG pelo nome
# response = ec2.describe_security_groups(
#     Filters=[{"Name": "group-name", "Values": [SG_NAME]}]
# )

# if response["SecurityGroups"]:
#     sg_id = response["SecurityGroups"][0]["GroupId"]

#     try:
#         ec2.delete_security_group(GroupId=sg_id)
#         print("SG deletado:", sg_id)
#     except Exception as e:
#         print("Erro ao deletar SG:", e)
# else:
#     print("SG não encontrado")