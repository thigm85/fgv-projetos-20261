"""
Script para carregar os dados do classicmodels no banco MySQL RDS.
Lê o arquivo SQL de exemplo e executa no banco provisionado.
"""

import sys
import boto3
import pymysql
from config import (
    RDS_INSTANCE_IDENTIFIER,
    RDS_MASTER_USERNAME,
    RDS_MASTER_PASSWORD,
    RDS_REGION,
    RDS_PORT,
    SQL_FILE_PATH,
)


def get_rds_endpoint():
    """Obtém o endpoint da instância RDS."""
    session = boto3.Session(region_name=RDS_REGION)
    rds_client = session.client("rds")
    response = rds_client.describe_db_instances(
        DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER
    )
    instance = response["DBInstances"][0]
    if instance["DBInstanceStatus"] != "available":
        print(f"Erro: instância não está disponível. Status: {instance['DBInstanceStatus']}")
        sys.exit(1)
    return instance["Endpoint"]["Address"]


def load_data():
    """Carrega o arquivo SQL no banco MySQL RDS."""
    endpoint = get_rds_endpoint()
    print(f"Conectando ao RDS: {endpoint}:{RDS_PORT}")

    # Lê o arquivo SQL
    print(f"Lendo arquivo SQL: {SQL_FILE_PATH}")
    with open(SQL_FILE_PATH, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Conecta ao MySQL (sem especificar database, pois o SQL cria o database)
    connection = pymysql.connect(
        host=endpoint,
        port=RDS_PORT,
        user=RDS_MASTER_USERNAME,
        password=RDS_MASTER_PASSWORD,
        autocommit=True,
        connect_timeout=10,
        charset="utf8mb4",
    )

    try:
        cursor = connection.cursor()

        # Executa cada statement separadamente
        statements = sql_content.split(";")
        total = len(statements)
        executed = 0
        for i, stmt in enumerate(statements):
            stmt = stmt.strip()
            if not stmt or stmt.startswith("/*") or stmt.startswith("--"):
                continue
            try:
                cursor.execute(stmt)
                executed += 1
            except pymysql.Error as e:
                # Ignorar erros de DROP TABLE IF NOT EXISTS e similares
                print(f"  Aviso no statement {i}: {e}")

        print(f"\nCarga concluída! {executed} statements executados de {total} no arquivo.")
    finally:
        connection.close()
        print("Conexão encerrada.")


if __name__ == "__main__":
    load_data()
