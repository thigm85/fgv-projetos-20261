#!/usr/bin/env python3
"""
simulate_new_orders.py
----------------------
Insere pedidos sintéticos no banco classicmodels para simular a chegada
de novos dados após a carga histórica do Assignment 1.

Regras:
  - orderDate estritamente posterior ao watermark atual (ou MAX(orderDate)).
  - Cada pedido tem pelo menos 1 linha em orderdetails.
  - quantityOrdered * priceEach = sales_amount (coerente com o star schema).
  - NÃO atualiza etl_watermark (responsabilidade do job Glue — Task 2).

Uso:
    python scripts/simulate_new_orders.py --count 5 --seed 42

Variáveis de ambiente (ver .env.example):
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
"""

import argparse
import logging
import os
import random
import sys
from datetime import date, timedelta

import pymysql
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host":        os.getenv("DB_HOST", "localhost"),
    "port":        int(os.getenv("DB_PORT", 3306)),
    "user":        os.getenv("DB_USER", "root"),
    "password":    os.getenv("DB_PASSWORD", ""),
    "database":    os.getenv("DB_NAME", "classicmodels"),
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit":  False,
}

PIPELINE_NAME = "classicmodels_sales"

SQL_WATERMARK_DATE = """
SELECT last_processed_order_date
FROM etl_watermark
WHERE pipeline_name = %(name)s;
"""

SQL_MAX_ORDER_DATE = "SELECT MAX(orderDate) AS max_date FROM orders;"

SQL_CUSTOMERS = "SELECT customerNumber FROM customers ORDER BY customerNumber;"

SQL_PRODUCTS = """
SELECT productCode, buyPrice, MSRP
FROM products
ORDER BY productCode;
"""

SQL_INSERT_ORDER = """
INSERT INTO orders
    (orderDate, requiredDate, shippedDate, status, comments, customerNumber)
VALUES
    (%(orderDate)s, %(requiredDate)s, %(shippedDate)s,
     %(status)s, %(comments)s, %(customerNumber)s);
"""

SQL_INSERT_ORDER_DETAIL = """
INSERT INTO orderdetails
    (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
VALUES
    (%(orderNumber)s, %(productCode)s, %(quantityOrdered)s,
     %(priceEach)s, %(orderLineNumber)s);
"""

def get_connection():
    return pymysql.connect(**DB_CONFIG)

def get_baseline_date(cursor) -> date:
    """
    Retorna a data base para novos pedidos:
    max(watermark.last_processed_order_date, MAX(orders.orderDate))
    """
    cursor.execute(SQL_WATERMARK_DATE, {"name": PIPELINE_NAME})
    row = cursor.fetchone()
    wm_date = row["last_processed_order_date"] if row else None

    cursor.execute(SQL_MAX_ORDER_DATE)
    row2 = cursor.fetchone()
    max_db = row2["max_date"] if row2 else None

    candidates = [d for d in [wm_date, max_db] if d is not None]
    if not candidates:
        log.error("Não foi possível determinar data base — banco pode estar vazio.")
        sys.exit(1)

    base = max(candidates)
    log.info(f"Data base para simulação: {base}  (watermark={wm_date}, max_db={max_db})")
    return base

def next_business_day(d: date) -> date:
    """Retorna o próximo dia útil após d (pula sáb/dom)."""
    d += timedelta(days=1)
    while d.weekday() >= 5:  # 5=sábado, 6=domingo
        d += timedelta(days=1)
    return d

def load_reference_data(cursor):
    cursor.execute(SQL_CUSTOMERS)
    customers = [r["customerNumber"] for r in cursor.fetchall()]

    cursor.execute(SQL_PRODUCTS)
    products = cursor.fetchall()

    if not customers or not products:
        log.error("Tabelas customers ou products estão vazias.")
        sys.exit(1)

    return customers, products

def build_order_details(rng, products, order_number, max_lines=3):
    """
    Gera entre 1 e max_lines linhas de orderdetails para um pedido.
    priceEach é sorteado entre buyPrice e MSRP (regra de negócio do A1).
    """
    n_lines = rng.randint(1, max_lines)
    chosen_products = rng.sample(products, min(n_lines, len(products)))
    details = []
    for line_num, prod in enumerate(chosen_products, start=1):
        buy_price = float(prod["buyPrice"])
        msrp = float(prod["MSRP"])
        # priceEach entre buyPrice e MSRP (ambos inclusos)
        price_each = round(rng.uniform(buy_price, msrp), 2)
        qty = rng.randint(1, 50)
        details.append(
            {
                "orderNumber":     order_number,
                "productCode":     prod["productCode"],
                "quantityOrdered": qty,
                "priceEach":       price_each,
                "orderLineNumber": line_num,
            }
        )
    return details

def parse_args():
    parser = argparse.ArgumentParser(description="Simula novos pedidos no classicmodels.")
    parser.add_argument(
        "--count", type=int, default=5,
        help="Número de pedidos a criar (default: 5).",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Semente para reprodutibilidade (opcional).",
    )
    return parser.parse_args()

def main():
    args = parse_args()
    rng = random.Random(args.seed)

    log.info("=== simulate_new_orders.py iniciado ===")
    log.info(f"  count={args.count}  seed={args.seed}")

    conn = get_connection()
    try:
        created_orders = []

        with conn.cursor() as cur:
            base_date = get_baseline_date(cur)
            customers, products = load_reference_data(cur)

            current_date = base_date 

            for i in range(args.count):
                current_date = next_business_day(current_date)

                required_date  = current_date + timedelta(days=rng.randint(7, 21))
                shipped_date   = current_date + timedelta(days=rng.randint(1, 5))
                customer_num   = rng.choice(customers)

                order_data = {
                    "orderDate":      current_date.isoformat(),
                    "requiredDate":   required_date.isoformat(),
                    "shippedDate":    shipped_date.isoformat(),
                    "status":         "Shipped",
                    "comments":       f"Simulated order {i + 1} — seed={args.seed}",
                    "customerNumber": customer_num,
                }

                cur.execute(SQL_INSERT_ORDER, order_data)
                order_number = conn.insert_id()  # equivale a LAST_INSERT_ID()

                details = build_order_details(rng, products, order_number)
                for det in details:
                    cur.execute(SQL_INSERT_ORDER_DETAIL, det)

                total_sales = sum(d["quantityOrdered"] * d["priceEach"] for d in details)
                created_orders.append(
                    {
                        "orderNumber":  order_number,
                        "orderDate":    current_date,
                        "customerNum":  customer_num,
                        "lines":        len(details),
                        "sales_amount": round(total_sales, 2),
                    }
                )
                log.info(
                    f"  Pedido #{order_number} criado | date={current_date} "
                    f"| customer={customer_num} | lines={len(details)} "
                    f"| sales_amount={total_sales:.2f}"
                )

            conn.commit()

        dates = [o["orderDate"] for o in created_orders]
        total_lines = sum(o["lines"] for o in created_orders)
        print("\n" + "=" * 60)
        print(f"RESUMO — {len(created_orders)} pedido(s) criado(s)")
        print(f"  IDs: {[o['orderNumber'] for o in created_orders]}")
        print(f"  Faixa de datas: {min(dates)}  →  {max(dates)}")
        print(f"  Total de linhas em orderdetails: {total_lines}")
        print("=" * 60 + "\n")

        log.info("=== simulate_new_orders.py concluído com sucesso ===")

    except Exception as exc:
        conn.rollback()
        log.error(f"Erro durante simulação: {exc}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
