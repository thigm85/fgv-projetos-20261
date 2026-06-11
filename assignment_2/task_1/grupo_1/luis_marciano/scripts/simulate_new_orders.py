import os
import argparse
import random
from datetime import timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

def get_engine():
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST')
    return create_engine(f"mysql+pymysql://{user}:{password}@{host}:3306/classicmodels")

def simulate_orders(count, seed):
    if seed is not None:
        random.seed(seed)

    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            # 1. Obter referências válidas para chaves estrangeiras
            customers = [row[0] for row in conn.execute(text("SELECT customerNumber FROM customers")).fetchall()]
            products = [(row[0], row[1]) for row in conn.execute(text("SELECT productCode, MSRP FROM products")).fetchall()]
            
            # 2. Obter o estado atual para gerar incrementos coerentes
            max_order_result = conn.execute(text("SELECT MAX(orderNumber), MAX(orderDate) FROM orders")).fetchone()
            current_max_order_id = max_order_result[0] or 10000
            current_max_date = max_order_result[1]
            
            watermark_result = conn.execute(text(
                "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'"
            )).fetchone()
            
            # A nova data base deve ser a maior entre o watermark e o último pedido da tabela
            base_date = watermark_result[0] if watermark_result and watermark_result[0] else current_max_date
            
            created_orders = []
            total_details = 0
            
            # 3. Gerar os novos pedidos (count)
            for i in range(count):
                current_max_order_id += 1
                new_order_id = current_max_order_id
                
                # Incrementa entre 1 e 3 dias a partir da base_date para simular a passagem do tempo
                order_date = base_date + timedelta(days=random.randint(1, 3))
                required_date = order_date + timedelta(days=random.randint(5, 10))
                
                customer_id = random.choice(customers)
                
                # Inserção na tabela Orders
                insert_order = text("""
                    INSERT INTO orders (orderNumber, orderDate, requiredDate, status, customerNumber)
                    VALUES (:id, :odate, :rdate, 'In Process', :cid)
                """)
                conn.execute(insert_order, {
                    "id": new_order_id, "odate": order_date, "rdate": required_date, "cid": customer_id
                })
                created_orders.append(new_order_id)
                
                # Inserção na tabela OrderDetails (1 a 3 itens por pedido)
                num_items = random.randint(1, 3)
                selected_products = random.sample(products, num_items)
                
                for line_num, (product_code, msrp) in enumerate(selected_products, start=1):
                    quantity = random.randint(10, 50)
                    insert_detail = text("""
                        INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                        VALUES (:oid, :pcode, :qty, :price, :line)
                    """)
                    conn.execute(insert_detail, {
                        "oid": new_order_id, "pcode": product_code, "qty": quantity, "price": msrp, "line": line_num
                    })
                    total_details += 1
                    
                # Atualiza a base_date para que os próximos pedidos no loop avancem no tempo
                base_date = order_date

            print("=== Resumo da Simulação ===")
            print(f"Pedidos gerados: {len(created_orders)} (IDs: {min(created_orders)} até {max(created_orders)})")
            print(f"Linhas inseridas em orderdetails: {total_details}")

    except SQLAlchemyError as e:
        print(f"Erro fatal durante a simulação (Rollback automático acionado): {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simula novos pedidos no banco classicmodels.")
    parser.add_argument("--count", type=int, default=5, help="Número de pedidos a criar.")
    parser.add_argument("--seed", type=int, default=None, help="Semente randômica para reprodutibilidade.")
    args = parser.parse_args()
    
    simulate_orders(args.count, args.seed)