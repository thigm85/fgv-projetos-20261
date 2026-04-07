"""
Script de validação: verifica se todas as tabelas do classicmodels foram criadas
e populadas corretamente no RDS.
"""

import sys
import boto3
import pymysql
from config import (
    RDS_INSTANCE_IDENTIFIER,
    RDS_DB_NAME,
    RDS_MASTER_USERNAME,
    RDS_MASTER_PASSWORD,
    RDS_REGION,
    RDS_PORT,
)

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


def get_rds_endpoint():
    """Obtém o endpoint da instância RDS."""
    session = boto3.Session(region_name=RDS_REGION)
    rds_client = session.client("rds")
    response = rds_client.describe_db_instances(
        DBInstanceIdentifier=RDS_INSTANCE_IDENTIFIER
    )
    return response["DBInstances"][0]["Endpoint"]["Address"]


def validate():
    """Valida as tabelas e dados no banco classicmodels."""
    endpoint = get_rds_endpoint()
    print(f"Conectando ao RDS: {endpoint}:{RDS_PORT}")

    connection = pymysql.connect(
        host=endpoint,
        port=RDS_PORT,
        user=RDS_MASTER_USERNAME,
        password=RDS_MASTER_PASSWORD,
        database=RDS_DB_NAME,
        connect_timeout=10,
        charset="utf8mb4",
    )

    all_ok = True
    try:
        cursor = connection.cursor()

        # Verificar tabelas existentes
        cursor.execute("SHOW TABLES")
        existing_tables = sorted([row[0] for row in cursor.fetchall()])
        print(f"\nTabelas encontradas: {existing_tables}")

        missing = set(EXPECTED_TABLES) - set(existing_tables)
        if missing:
            print(f"ERRO: Tabelas faltando: {missing}")
            all_ok = False
        else:
            print("OK: Todas as tabelas esperadas existem.")

        # Contagem de registros por tabela
        print(f"\n{'Tabela':<20} {'Registros':>10}")
        print("-" * 32)
        for table in EXPECTED_TABLES:
            if table in existing_tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                count = cursor.fetchone()[0]
                print(f"{table:<20} {count:>10}")
                if count == 0:
                    print(f"  AVISO: tabela '{table}' está vazia!")
                    all_ok = False
            else:
                print(f"{table:<20} {'MISSING':>10}")
                all_ok = False

    finally:
        connection.close()

    print()
    if all_ok:
        print("VALIDAÇÃO OK: Todas as tabelas foram criadas e populadas corretamente!")
    else:
        print("VALIDAÇÃO FALHOU: Verifique os erros acima.")
        sys.exit(1)


if __name__ == "__main__":
    validate()
