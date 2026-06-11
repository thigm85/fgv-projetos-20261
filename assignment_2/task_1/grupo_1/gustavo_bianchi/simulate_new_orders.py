import os
import pymysql
import argparse
import random
import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Order Simulator] %(message)s', datefmt='%H:%M:%S')

# Para conseguir reaproveitar o endpoint gerado na task 1 do ass. 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENDPOINT_PATH = os.path.abspath(os.path.join(BASE_DIR, "../../../../assignment_1/task_1/grupo_1/gustavo_bianchi/rds_endpoint.txt"))

def get_rds_endpoint():
    if not os.path.exists(ENDPOINT_PATH):
        raise FileNotFoundError(f"Endpoint não encontrado: {ENDPOINT_PATH}")
    with open(ENDPOINT_PATH, "r") as f:
        return f.read().strip()

def simulate_orders(count, seed):
    if seed is not None:
        random.seed(seed)
        logging.info(f"Random seed configurada: {seed}")

    endpoint = get_rds_endpoint()
    db_password = os.environ.get("TF_VAR_db_password")
    
    if not db_password:
        raise ValueError("Variável 'TF_VAR_db_password' não configurada.")

    connection = pymysql.connect(
        host=endpoint, user="admin", password=db_password, database="classicmodels", cursorclass=pymysql.cursors.DictCursor
    )

    try:
        with connection.cursor() as cursor:
            # Obtém os clientes e produtos existentes na base
            cursor.execute("SELECT customerNumber FROM customers;")
            customers = [row['customerNumber'] for row in cursor.fetchall()]

            cursor.execute("SELECT productCode, MSRP FROM products;")
            products = cursor.fetchall()

            if not customers or not products:
                raise ValueError("Tabelas 'customers' ou 'products' estão vazias.")

            # Pega a data mínima em que os pedidos devem ser simulados
            cursor.execute("SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales';")
            wm_result = cursor.fetchone()
            wm_date = wm_result['last_processed_order_date'] if wm_result else datetime.date(2000, 1, 1)

            cursor.execute("SELECT MAX(orderDate) as max_date FROM orders;")
            order_result = cursor.fetchone()
            max_order_date = order_result['max_date'] if order_result and order_result['max_date'] else datetime.date(2000, 1, 1)

            base_date = max(wm_date, max_order_date)

            # Cria o próximo id pra compra 
            cursor.execute("SELECT MAX(orderNumber) as max_id FROM orders;")
            max_id_result = cursor.fetchone()
            next_order_id = (max_id_result['max_id'] or 0) + 1

            created_orders = []
            total_order_details = 0
            start_simulation_date = None
            end_simulation_date = None

            # Loop de criação dos pedidos novos 
            logging.info(f"Iniciando simulação de {count} pedido(s)...")
            
            for i in range(count):
                current_order_id = next_order_id + i
                
                # Incrementa dias sequencialmente para simular o passar do tempo
                days_to_add = random.randint(1, 3)
                order_date = base_date + datetime.timedelta(days=i + days_to_add)
                
                if i == 0: start_simulation_date = order_date
                end_simulation_date = order_date

                customer_id = random.choice(customers)

                # Insert na tabela 'orders'
                insert_order_sql = """
                INSERT INTO orders (orderNumber, orderDate, requiredDate, status, customerNumber)
                VALUES (%s, %s, %s, 'In Process', %s);
                """
                required_date = order_date + datetime.timedelta(days=7)
                cursor.execute(insert_order_sql, (current_order_id, order_date, required_date, customer_id))
                created_orders.append(current_order_id)

                # Insert na tabela 'orderdetails' (1 a 3 itens por pedido)
                items_count = random.randint(1, 3)
                for item_line in range(1, items_count + 1):
                    product = random.choice(products)
                    qty = random.randint(10, 50)
                    price = product['MSRP'] # Mantém coerência de preço
                    
                    insert_detail_sql = """
                    INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                    VALUES (%s, %s, %s, %s, %s);
                    """
                    cursor.execute(insert_detail_sql, (current_order_id, product['productCode'], qty, price, item_line))
                    total_order_details += 1

            connection.commit()

            # Resumo da operação
            logging.info("--- Resumo da Simulação ---")
            logging.info(f"Pedidos criados (IDs): {min(created_orders)} até {max(created_orders)}")
            logging.info(f"Faixa de Datas: {start_simulation_date} a {end_simulation_date}")
            logging.info(f"Linhas em 'orderdetails': {total_order_details}")
            logging.info("---------------------------")

    except Exception as e:
        connection.rollback()
        logging.error(f"Erro durante a simulação: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simula novos pedidos no banco classicmodels.")
    parser.add_argument('--count', type=int, default=5, help="Número de pedidos a criar.")
    parser.add_argument('--seed', type=int, default=None, help="Semente de geração randômica para reprodutibilidade.")
    
    args = parser.parse_args()
    simulate_orders(args.count, args.seed)