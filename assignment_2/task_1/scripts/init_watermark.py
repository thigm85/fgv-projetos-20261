"""
Script para inicializar a tabela de watermark no banco MySQL RDS.
Cria a tabela etl_watermark se não existir e insere o registro inicial.
"""

import sys
import os
from pathlib import Path

# Adicionar diretório pai ao path para importar config
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import pymysql
from datetime import datetime
from config import (
    RDS_INSTANCE_IDENTIFIER,
    RDS_DB_NAME,
    RDS_MASTER_USERNAME,
    RDS_MASTER_PASSWORD,
    RDS_REGION,
    RDS_PORT,
    WATERMARK_TABLE,
    PIPELINE_NAME,
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


def init_watermark():
    """Inicializa a tabela de watermark no banco de dados."""
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
        autocommit=False,
    )

    try:
        cursor = connection.cursor()

        # 1. Criar tabela se não existir
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{WATERMARK_TABLE}` (
            `pipeline_name` VARCHAR(64) PRIMARY KEY,
            `last_processed_order_date` DATE NOT NULL,
            `last_run_at` DATETIME NOT NULL,
            `last_run_status` VARCHAR(32) NOT NULL DEFAULT 'NEVER_RUN'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        print(f"Criando/verificando tabela '{WATERMARK_TABLE}'...")
        cursor.execute(create_table_sql)
        connection.commit()
        print(f"OK: Tabela '{WATERMARK_TABLE}' pronta.")

        # 2. Verificar se o registro inicial já existe
        check_sql = f"SELECT COUNT(*) FROM `{WATERMARK_TABLE}` WHERE `pipeline_name` = %s"
        cursor.execute(check_sql, (PIPELINE_NAME,))
        exists = cursor.fetchone()[0] > 0

        if exists:
            print(f"INFO: Pipeline '{PIPELINE_NAME}' já inicializado no watermark.")
        else:
            # 3. Obter MAX(orders.orderDate) como baseline
            cursor.execute("SELECT MAX(orderDate) FROM `orders`")
            max_order_date = cursor.fetchone()[0]

            if max_order_date is None:
                print("ERRO: Tabela 'orders' está vazia. Não é possível inicializar o watermark.")
                sys.exit(1)

            print(f"MAX(orders.orderDate) encontrado: {max_order_date}")

            # 4. Inserir registro inicial
            now_utc = datetime.utcnow()
            insert_sql = f"""
            INSERT INTO `{WATERMARK_TABLE}` 
            (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
            VALUES (%s, %s, %s, 'NEVER_RUN')
            """
            cursor.execute(insert_sql, (PIPELINE_NAME, max_order_date, now_utc))
            connection.commit()
            print(f"OK: Pipeline '{PIPELINE_NAME}' inicializado com watermark em {max_order_date}.")

        print("\nINICIALIZAÇÃO DE WATERMARK CONCLUÍDA COM SUCESSO!")

    except pymysql.Error as e:
        print(f"Erro ao executar SQL: {e}")
        connection.rollback()
        sys.exit(1)
    finally:
        connection.close()
        print("Conexão encerrada.")


if __name__ == "__main__":
    init_watermark()
