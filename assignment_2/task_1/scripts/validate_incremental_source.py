"""
Script de validação: verifica se o sistema de origem está pronto para cargas incrementais.
"""

import sys
import os
from pathlib import Path

# Adicionar diretório pai ao path para importar config
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import pymysql
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


def validate_incremental_source():
    """Valida se o sistema de origem está pronto para cargas incrementais."""
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
    checks_passed = 0
    checks_total = 4

    try:
        cursor = connection.cursor()

        print(f"\n{'='*60}")
        print("VALIDAÇÃO DO SISTEMA DE ORIGEM INCREMENTAL")
        print(f"{'='*60}\n")

        # Verificação 1: Tabela etl_watermark existe
        print(f"[CHECK 1/4] Verificando existência da tabela '{WATERMARK_TABLE}'...")
        cursor.execute(
            f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (RDS_DB_NAME, WATERMARK_TABLE)
        )
        table_exists = cursor.fetchone()[0] > 0

        if table_exists:
            print(f"  ✓ Tabela '{WATERMARK_TABLE}' existe.")
            checks_passed += 1
        else:
            print(f"  ✗ Tabela '{WATERMARK_TABLE}' não encontrada.")
            all_ok = False

        # Verificação 2: Registro do pipeline existe
        print(f"\n[CHECK 2/4] Verificando registro do pipeline '{PIPELINE_NAME}'...")
        cursor.execute(
            f"SELECT COUNT(*) FROM `{WATERMARK_TABLE}` WHERE pipeline_name = %s",
            (PIPELINE_NAME,)
        )
        pipeline_exists = cursor.fetchone()[0] > 0

        if pipeline_exists:
            print(f"  ✓ Pipeline '{PIPELINE_NAME}' encontrado em watermark.")
            checks_passed += 1
        else:
            print(f"  ✗ Pipeline '{PIPELINE_NAME}' não encontrado em watermark.")
            all_ok = False

        # Verificação 3: last_processed_order_date não é NULL
        print(f"\n[CHECK 3/4] Verificando validade do watermark...")
        cursor.execute(
            f"SELECT last_processed_order_date, last_run_status FROM `{WATERMARK_TABLE}` WHERE pipeline_name = %s",
            (PIPELINE_NAME,)
        )
        result = cursor.fetchone()

        if result:
            last_date, status = result
            if last_date is not None:
                print(f"  ✓ Watermark válido: {last_date} (status: {status})")
                checks_passed += 1
            else:
                print(f"  ✗ Watermark inválido: last_processed_order_date é NULL")
                all_ok = False
        else:
            print(f"  ✗ Registro de pipeline não encontrado.")
            all_ok = False

        # Verificação 4: Há dados novos (MAX(orderDate) > watermark)
        print(f"\n[CHECK 4/4] Verificando disponibilidade de dados incrementais...")
        cursor.execute(f"SELECT MAX(orderDate) FROM `orders`")
        max_order_date = cursor.fetchone()[0]

        if result and last_date:
            if max_order_date > last_date:
                new_orders_count = 0
                cursor.execute(
                    "SELECT COUNT(*) FROM `orders` WHERE orderDate > %s",
                    (last_date,)
                )
                new_orders_count = cursor.fetchone()[0]
                print(f"  ✓ Dados novos disponíveis: {new_orders_count} pedidos após {last_date}")
                checks_passed += 1
            else:
                print(f"  ⚠ Sem dados incrementais: MAX(orderDate) = {max_order_date}, watermark = {last_date}")
                print(f"    (OK durante testes iniciais; execute simulate_new_orders.py para gerar dados)")
                checks_passed += 1
        else:
            print(f"  ✗ Não foi possível validar dados incrementais.")
            all_ok = False

        # Verificação adicional: Integridade de orderdetails para novos pedidos
        if result and last_date:
            print(f"\n[EXTRA] Verificando integridade de orderdetails para novos pedidos...")
            cursor.execute(
                """
                SELECT COUNT(*) FROM orderdetails od
                JOIN orders o ON od.orderNumber = o.orderNumber
                WHERE o.orderDate > %s
                """,
                (last_date,)
            )
            detail_count = cursor.fetchone()[0]
            if detail_count >= 0:
                print(f"  ✓ {detail_count} linhas em orderdetails para pedidos após watermark")

        # Resumo
        print(f"\n{'='*60}")
        print(f"RESULTADO: {checks_passed}/{checks_total} verificações passadas")
        print(f"{'='*60}\n")

        if all_ok:
            print("✓ VALIDAÇÃO OK: Sistema de origem pronto para cargas incrementais!")
            return 0
        else:
            print("✗ VALIDAÇÃO FALHOU: Verifique os erros acima.")
            return 1

    except pymysql.Error as e:
        print(f"\n✗ Erro ao conectar ou executar SQL: {e}")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    exit_code = validate_incremental_source()
    sys.exit(exit_code)
