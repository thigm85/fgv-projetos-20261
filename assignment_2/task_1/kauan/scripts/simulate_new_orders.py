#!/usr/bin/env python3
import os
import sys
import argparse
import random
import datetime
import pymysql
import pymysql.cursors

def load_rds_config(filename: str = "rds_connection.env") -> dict:
    current_dir = os.path.abspath(os.path.dirname(__file__))
    while current_dir:
        filepath = os.path.join(current_dir, filename)
        if os.path.isfile(filepath):
            env = {}
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        env[key.strip()] = val.strip()
            return env
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir
    return {}

def get_next_business_day(start_date: datetime.date) -> datetime.date:
    current = start_date + datetime.timedelta(days=1)
    while current.weekday() >= 5: # 5 is Saturday, 6 is Sunday
        current += datetime.timedelta(days=1)
    return current

def main():
    parser = argparse.ArgumentParser(description="Simula a criação de novos pedidos no banco classicmodels.")
    parser.add_argument("--count", type=int, default=5, help="Número de pedidos a criar (default: 5)")
    parser.add_argument("--seed", type=int, default=None, help="Semente para geração pseudo-aleatória de dados")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"=== Simulando {args.count} Novos Pedidos ===")
    cfg = load_rds_config()
    
    if not cfg.get("RDS_HOST"):
        print("[ERRO] Configurações do RDS não encontradas no rds_connection.env.", file=sys.stderr)
        sys.exit(1)

    try:
        conn = pymysql.connect(
            host=cfg.get("RDS_HOST"),
            port=int(cfg.get("RDS_PORT", 3306)),
            user=cfg.get("RDS_USER"),
            password=cfg.get("RDS_PASSWORD"),
            database=cfg.get("RDS_DB"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao RDS: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            # 1. Obter clientes e produtos válidos
            cur.execute("SELECT customerNumber FROM customers")
            customers = [row["customerNumber"] for row in cur.fetchall()]
            if not customers:
                print("[ERRO] Nenhum cliente encontrado no banco de dados.", file=sys.stderr)
                sys.exit(1)

            cur.execute("SELECT productCode, buyPrice, MSRP FROM products")
            products = cur.fetchall()
            if not products:
                print("[ERRO] Nenhum produto encontrado no banco de dados.", file=sys.stderr)
                sys.exit(1)

            # 2. Determinar a data base
            cur.execute("SELECT MAX(orderDate) as max_date FROM orders")
            max_order_date = cur.fetchone()["max_date"]

            # Verificar se a tabela de watermark existe
            cur.execute("""
                SELECT COUNT(*) as count FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = 'etl_watermark'
            """, (cfg.get("RDS_DB"),))
            has_watermark_table = cur.fetchone()["count"] > 0

            watermark_date = None
            if has_watermark_table:
                cur.execute("SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'")
                row = cur.fetchone()
                if row:
                    watermark_date = row["last_processed_order_date"]

            # Determinar a data de início da simulação
            base_date = None
            if max_order_date and watermark_date:
                base_date = max(max_order_date, watermark_date)
            elif max_order_date:
                base_date = max_order_date
            elif watermark_date:
                base_date = watermark_date
            else:
                base_date = datetime.date(2005, 5, 31)

            # Para manter "dias úteis recentes", se a base_date for muito antiga (ex: antes de 2026),
            # nós podemos saltar para uma data recente (ex: 30 dias atrás) contanto que seja estritamente posterior a base_date.
            today = datetime.date.today()
            recent_start = today - datetime.timedelta(days=30)
            if base_date < recent_start:
                current_date = recent_start
                while current_date.weekday() >= 5:
                    current_date += datetime.timedelta(days=1)
            else:
                current_date = get_next_business_day(base_date)

            # 3. Obter o maior orderNumber atual
            cur.execute("SELECT MAX(orderNumber) as max_num FROM orders")
            max_order_number = cur.fetchone()["max_num"]
            if max_order_number is None:
                max_order_number = 10000 # fallback inicial

            created_orders = []
            total_orderdetails_rows = 0
            date_range_start = current_date

            # Executa inserções dentro de uma transação
            for i in range(args.count):
                next_order_number = max_order_number + 1 + i
                cust_num = random.choice(customers)
                
                # Inserir pedido
                # requiredDate = orderDate + 7 dias
                req_date = current_date + datetime.timedelta(days=7)
                
                insert_order_sql = """
                INSERT INTO orders (orderNumber, orderDate, requiredDate, shippedDate, status, comments, customerNumber)
                VALUES (%s, %s, %s, NULL, 'In Process', 'Simulated incremental order', %s)
                """
                cur.execute(insert_order_sql, (next_order_number, current_date, req_date, cust_num))
                
                # Inserir orderdetails (entre 1 e 3 produtos por pedido)
                num_products = random.randint(1, 3)
                chosen_products = random.sample(products, num_products)
                
                for idx, prod in enumerate(chosen_products):
                    prod_code = prod["productCode"]
                    # preço de venda entre buyPrice e MSRP
                    buy_price = float(prod["buyPrice"])
                    msrp = float(prod["MSRP"])
                    price_each = round(random.uniform(buy_price, msrp), 2)
                    qty = random.randint(1, 10)
                    line_num = idx + 1
                    
                    insert_detail_sql = """
                    INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                    VALUES (%s, %s, %s, %s, %s)
                    """
                    cur.execute(insert_detail_sql, (next_order_number, prod_code, qty, price_each, line_num))
                    total_orderdetails_rows += 1

                created_orders.append(next_order_number)
                date_range_end = current_date
                
                # Incrementar para o próximo dia útil
                current_date = get_next_business_day(current_date)

            conn.commit()

            print(f"[OK] {args.count} pedidos simulados com sucesso na transação.")
            print("\n=== Resumo da Simulação ===")
            print(f"IDs dos pedidos criados: {created_orders}")
            print(f"Faixa de datas dos novos pedidos: {date_range_start} até {date_range_end}")
            print(f"Total de itens (linhas em orderdetails): {total_orderdetails_rows}")

    except Exception as e:
        conn.rollback()
        print(f"[ERRO] Falha ao simular novos pedidos: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
