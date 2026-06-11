import os
import argparse
import random
from datetime import timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = 'classicmodels'
DB_PORT = "3306"

def get_args():
    parser = argparse.ArgumentParser(description="Simulate new orders for classicmodels.")
    parser.add_argument("--count", type=int, default=5, help="Number of orders to generate (default: 5)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    return parser.parse_args()

def simulate_orders():
    args = get_args()
    
    if args.seed is not None:
        random.seed(args.seed)

    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)

    try:
        with engine.begin() as connection:
            # Fetch reference data
            max_order_query = connection.execute(text("SELECT MAX(orderNumber) FROM orders")).scalar()
            max_date_query = connection.execute(text("SELECT MAX(orderDate) FROM orders")).scalar()
            
            customers = [row[0] for row in connection.execute(text("SELECT customerNumber FROM customers")).fetchall()]
            products = connection.execute(text("SELECT productCode, MSRP FROM products")).fetchall()

            if not customers or not products:
                raise ValueError("Reference data (customers or products) is missing.")

            current_order_id = max_order_query if max_order_query else 10000
            current_date = max_date_query
            
            generated_order_ids = []
            total_details_inserted = 0

            # Generate and insert new orders
            for i in range(args.count):
                current_order_id += 1
                # Incrementing the date by 1 to 3 days to simulate passage of time
                current_date += timedelta(days=random.randint(1, 3))
                customer_id = random.choice(customers)

                insert_order_sql = text("""
                    INSERT INTO orders (orderNumber, orderDate, requiredDate, status, customerNumber)
                    VALUES (:order_id, :order_date, :req_date, 'Shipped', :cust_id)
                """)
                
                connection.execute(insert_order_sql, {
                    "order_id": current_order_id,
                    "order_date": current_date,
                    "req_date": current_date + timedelta(days=5),
                    "cust_id": customer_id
                })

                generated_order_ids.append(current_order_id)

                # Generating details for the current order
                num_items = random.randint(1, 4)
                selected_products = random.sample(products, num_items)
                
                for line_number, product in enumerate(selected_products, start=1):
                    product_code = product[0]
                    price_each = product[1] 
                    qty = random.randint(10, 50)

                    insert_detail_sql = text("""
                        INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                        VALUES (:order_id, :prod_code, :qty, :price, :line_num)
                    """)
                    connection.execute(insert_detail_sql, {
                        "order_id": current_order_id,
                        "prod_code": product_code,
                        "qty": qty,
                        "price": price_each,
                        "line_num": line_number
                    })
                    total_details_inserted += 1

            # Summary
            print(f"=== Simulation Summary ===")
            print(f"Orders generated: {args.count}")
            print(f"Order IDs: {min(generated_order_ids)} to {max(generated_order_ids)}")
            print(f"Date range: {max_date_query + timedelta(days=1)} to {current_date}")
            print(f"OrderDetails rows inserted: {total_details_inserted}")

    except SQLAlchemyError as e:
        print(f"Database error occurred. Transaction rolled back. Details: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    simulate_orders()