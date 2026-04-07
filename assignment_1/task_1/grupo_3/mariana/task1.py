import boto3
import pymysql
import requests

REGION = "us-east-1"
DB_ID = "task1-mysql"
USERNAME = "mariana"
PASSWORD = "password123"

EXPECTED_TABLES = [
    "customers",
    "employees",
    "offices",
    "orderdetails",
    "orders",
    "payments",
    "productlines",
    "products",
]

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

            print("\nIniciando validacao das tabelas...")

            cursor.execute("USE classicmodels;")
            cursor.execute("SHOW TABLES;")
            created_tables = {row[0] for row in cursor.fetchall()}

            missing_tables = sorted(set(EXPECTED_TABLES) - created_tables)
            unexpected_tables = sorted(created_tables - set(EXPECTED_TABLES))

            if missing_tables:
                raise RuntimeError(
                    f"Tabelas ausentes apos a carga: {', '.join(missing_tables)}"
                )

            if unexpected_tables:
                print(
                    "Tabelas adicionais encontradas:",
                    ", ".join(unexpected_tables)
                )

            empty_tables = []
            for table in EXPECTED_TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
                row_count = cursor.fetchone()[0]
                print(f"[VALIDACAO] Tabela `{table}` com {row_count} registros.")
                if row_count == 0:
                    empty_tables.append(table)

            if empty_tables:
                raise RuntimeError(
                    f"Tabelas criadas, mas vazias: {', '.join(empty_tables)}"
                )

            print("Validacao concluida com sucesso: todas as tabelas foram criadas e populadas.")
    finally:
        conn.close()

    print("Carga concluída.")