"""
Script para simular novos pedidos no banco MySQL RDS.
Insere pedidos com datas posteriores ao watermark.
"""

import sys
import os
from pathlib import Path
import argparse
import random

# Adicionar diretório pai ao path para importar config
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import pymysql
from datetime import datetime, timedelta
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


def get_next_order_date(connection, watermark_date):
    """Obtém a próxima data válida para um novo pedido (dia útil após watermark)."""
    next_date = watermark_date + timedelta(days=1)
    
    # Se for fim de semana (5=sábado, 6=domingo), avança para segunda
    while next_date.weekday() >= 5:
        next_date += timedelta(days=1)
    
    return next_date


def get_random_customers_and_products(connection):
    """Retorna listas de customerNumbers e productCodes válidos do banco."""
    cursor = connection.cursor()
    
    cursor.execute("SELECT DISTINCT customerNumber FROM customers LIMIT 100")
    customers = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("SELECT DISTINCT productCode FROM products LIMIT 100")
    products = [row[0] for row in cursor.fetchall()]
    
    if not customers or not products:
        print("ERRO: Não há customers ou products suficientes para simular pedidos.")
        sys.exit(1)
    
    return customers, products


def simulate_new_orders(count=5, seed=None):
    """Simula inserção de novos pedidos no banco de dados."""
    if seed is not None:
        random.seed(seed)
        print(f"Seed definida para reprodutibilidade: {seed}")

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
        
        # 1. Obter customers e products
        customers, products = get_random_customers_and_products(connection)
        print(f"Found {len(customers)} active customers and {len(products)} products.")
        
        # 2. Obter watermark atual
        cursor.execute(
            f"SELECT last_processed_order_date FROM `{WATERMARK_TABLE}` WHERE pipeline_name = %s",
            (PIPELINE_NAME,)
        )
        result = cursor.fetchone()
        if result is None:
            print(f"ERRO: Pipeline '{PIPELINE_NAME}' não encontrado em watermark.")
            print("Execute init_watermark.py primeiro.")
            sys.exit(1)
        
        watermark_date = result[0]
        print(f"Watermark atual: {watermark_date}")
        
        # 3. Simular novos pedidos
        created_order_ids = []
        created_details_count = 0
        current_date = watermark_date
        
        print(f"\nInserindo {count} novos pedidos...")
        
        for i in range(count):
            # Próxima data (dia útil)
            current_date = get_next_order_date(connection, current_date)
            
            # Escolher cliente e produto aleatório
            customer_number = random.choice(customers)
            product_code = random.choice(products)
            
            # Quantidade aleatória (1-10)
            quantity_ordered = random.randint(1, 10)
            
            # Obter preço do produto
            cursor.execute("SELECT buyPrice FROM products WHERE productCode = %s", (product_code,))
            buy_price_result = cursor.fetchone()
            if buy_price_result:
                price_each = float(buy_price_result[0]) * random.uniform(1.2, 2.0)  # Margem de lucro
            else:
                price_each = 100.0
            
            # Status do pedido (aleatório)
            statuses = ["Shipped", "Processing", "Cancelled"]
            status = random.choice(statuses)
            
            try:
                # Obter o próximo orderNumber disponível
                cursor.execute("SELECT COALESCE(MAX(orderNumber), 10000) + 1 FROM orders")
                order_number = cursor.fetchone()[0]
                
                # Inserir ordem (usando transação)
                insert_order_sql = """
                INSERT INTO orders (orderNumber, customerNumber, orderDate, requiredDate, shippedDate, status, comments)
                VALUES (%s, %s, %s, %s, %s, %s, NULL)
                """
                required_date = current_date + timedelta(days=random.randint(5, 15))
                shipped_date = current_date + timedelta(days=random.randint(1, 7)) if status != "Cancelled" else None
                
                cursor.execute(
                    insert_order_sql,
                    (order_number, customer_number, current_date, required_date, shipped_date, status)
                )
                created_order_ids.append(order_number)
                
                # Inserir orderdetails (1 linha por order nesta simulação)
                insert_detail_sql = """
                INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                VALUES (%s, %s, %s, %s, 1)
                """
                cursor.execute(
                    insert_detail_sql,
                    (order_number, product_code, quantity_ordered, price_each)
                )
                created_details_count += 1
                
                print(f"  [{i+1}/{count}] Ordem #{order_number} criada (data: {current_date}, cliente: {customer_number})")
                
            except pymysql.Error as e:
                print(f"  ERRO ao inserir ordem: {e}")
                connection.rollback()
                sys.exit(1)
        
        # Commit de todas as transações
        connection.commit()
        
        # 4. Resumo
        print(f"\n{'='*60}")
        print("RESUMO DA SIMULAÇÃO")
        print(f"{'='*60}")
        print(f"Pedidos criados: {len(created_order_ids)}")
        print(f"IDs dos pedidos: {created_order_ids}")
        print(f"Linhas em orderdetails criadas: {created_details_count}")
        print(f"Faixa de datas: {watermark_date + timedelta(days=1)} a {current_date}")
        print(f"{'='*60}")
        print("SIMULAÇÃO CONCLUÍDA COM SUCESSO!")

    except pymysql.Error as e:
        print(f"Erro ao conectar ou executar SQL: {e}")
        connection.rollback()
        sys.exit(1)
    finally:
        connection.close()
        print("Conexão encerrada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Simula novos pedidos no banco classicmodels."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Número de pedidos a criar (padrão: 5)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed para reprodutibilidade (opcional)"
    )
    
    args = parser.parse_args()
    simulate_new_orders(count=args.count, seed=args.seed)
