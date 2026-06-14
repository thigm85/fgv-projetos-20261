import os
import argparse
import random
import pymysql
from datetime import timedelta

def get_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASS', ''),
        database=os.environ.get('DB_NAME', 'classicmodels'),
        cursorclass=pymysql.cursors.DictCursor
    )

def simulate_orders(count, seed):
    if seed is not None:
        random.seed(seed)

    connection = get_connection()
    created_orders = []
    total_details = 0
    
    try:
        with connection.cursor() as cursor:
            # Busca a maior data atual ou watermark
            cursor.execute("SELECT MAX(orderDate) as max_date FROM orders;")
            max_date = cursor.fetchone()['max_date']
            
            # Busca clientes elegíveis
            cursor.execute("SELECT customerNumber FROM customers;")
            customers = [row['customerNumber'] for row in cursor.fetchall()]
            
            # Busca produtos elegíveis
            cursor.execute("SELECT productCode, MSRP FROM products;")
            products = cursor.fetchall()
            
            # Determina o próximo orderNumber
            cursor.execute("SELECT MAX(orderNumber) as max_id FROM orders;")
            next_order_id = (cursor.fetchone()['max_id'] or 10000) + 1

            for i in range(count):
                customer = random.choice(customers)
                order_date = max_date + timedelta(days=random.randint(1, 5))
                required_date = order_date + timedelta(days=7)
                
                # Insere em orders
                insert_order_query = """
                INSERT INTO orders (orderNumber, orderDate, requiredDate, status, comments, customerNumber)
                VALUES (%s, %s, %s, 'In Process', 'Simulated order', %s);
                """
                cursor.execute(insert_order_query, (next_order_id, order_date, required_date, customer))
                
                # Insere orderdetails
                num_items = random.randint(1, 4)
                sampled_products = random.sample(products, num_items)
                
                for line_num, prod in enumerate(sampled_products, start=1):
                    qty = random.randint(10, 50)
                    price = prod['MSRP']
                    
                    insert_detail_query = """
                    INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                    VALUES (%s, %s, %s, %s, %s);
                    """
                    cursor.execute(insert_detail_query, (next_order_id, prod['productCode'], qty, price, line_num))
                    total_details += 1
                
                created_orders.append((next_order_id, order_date))
                next_order_id += 1
                max_date = order_date

            connection.commit()
            
            print(f"--- Resumo da simulação ---")
            print(f"Pedidos criados: {len(created_orders)}")
            print(f"IDs dos pedidos: {[o[0] for o in created_orders]}")
            if created_orders:
                print(f"Faixa de datas: {created_orders[0][1]} a {created_orders[-1][1]}")
            print(f"Linhas criadas em orderdetails: {total_details}")
            
    finally:
        connection.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Simula a entrada de novos pedidos no classicmodels.')
    parser.add_argument('--count', type=int, default=5, help='Número de pedidos a criar.')
    parser.add_argument('--seed', type=int, default=None, help='Seed para reprodutibilidade.')
    args = parser.parse_args()
    
    simulate_orders(args.count, args.seed)