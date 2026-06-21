import argparse
import logging
import os
import random
import sys
from datetime import date, datetime, timedelta

import mysql.connector
from dotenv import find_dotenv, load_dotenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Search and load .env
dotenv_path = find_dotenv()
if not dotenv_path:
    for path in [".env", "src/.env", "../src/.env", "../../src/.env"]:
        if os.path.exists(path):
            dotenv_path = path
            break

if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv()


def get_db_connection():
    db_host = os.getenv("DB_HOST")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")

    if not all([db_host, db_user, db_pass, db_name]):
        logger.error("Erro: Variáveis de conexão ao banco de dados incompletas no .env")
        sys.exit(1)

    return mysql.connector.connect(
        host=db_host, user=db_user, password=db_pass, database=db_name, use_pure=True
    )


def main():
    parser = argparse.ArgumentParser(
        description="Simula a criação de novos pedidos no classicmodels."
    )
    parser.add_argument(
        "--count", type=int, default=5, help="Número de pedidos a simular (default: 5)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semente para geração aleatória (opcional)",
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        logger.info(f"Usando seed aleatória: {args.seed}")

    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # 1. Buscar clientes existentes
        cursor.execute("SELECT customerNumber FROM customers")
        customers = [row[0] for row in cursor.fetchall()]
        if not customers:
            raise ValueError("Nenhum cliente cadastrado no banco de dados.")

        # 2. Buscar produtos existentes com preço
        cursor.execute("SELECT productCode, MSRP FROM products")
        products = [row for row in cursor.fetchall()]
        if not products:
            raise ValueError("Nenhum produto cadastrado no banco de dados.")

        # 3. Determinar o watermark atual e a data máxima de pedidos
        pipeline_name = "classicmodels_sales"
        cursor.execute(
            "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
            (pipeline_name,),
        )
        watermark_row = cursor.fetchone()
        watermark_date = watermark_row[0] if watermark_row else None

        cursor.execute("SELECT MAX(orderDate) FROM orders")
        max_order_date_row = cursor.fetchone()
        max_order_date = max_order_date_row[0] if max_order_date_row else None

        # Determinar a data de referência inicial (o maior entre watermark e data máxima)
        ref_date = date(2003, 1, 1)  # Fallback padrão caso não exista nada
        if watermark_date and max_order_date:
            ref_date = max(watermark_date, max_order_date)
        elif watermark_date:
            ref_date = watermark_date
        elif max_order_date:
            ref_date = max_order_date

        logger.info(
            f"Watermark atual: {watermark_date}, Data máxima no banco: {max_order_date}. Data de referência: {ref_date}"
        )

        # 4. Determinar o próximo orderNumber
        cursor.execute("SELECT MAX(orderNumber) FROM orders")
        max_order_number_row = cursor.fetchone()
        next_order_number = (
            max_order_number_row[0]
            if max_order_number_row and max_order_number_row[0] is not None
            else 10000
        ) + 1

        simulated_orders = []
        total_details_count = 0
        min_simulated_date = None
        max_simulated_date = None

        logger.info(
            f"Simulando {args.count} novos pedidos a partir do número {next_order_number}..."
        )

        for i in range(args.count):
            order_num = next_order_number + i
            # Gerar orderDate estritamente posterior (incrementando dia a dia)
            order_date = ref_date + timedelta(days=i + 1)

            # Formatos de data
            required_date = order_date + timedelta(days=7)

            if min_simulated_date is None or order_date < min_simulated_date:
                min_simulated_date = order_date
            if max_simulated_date is None or order_date > max_simulated_date:
                max_simulated_date = order_date

            customer_num = random.choice(customers)

            # Inserir pedido
            insert_order_query = """
            INSERT INTO orders (orderNumber, orderDate, requiredDate, shippedDate, status, comments, customerNumber)
            VALUES (%s, %s, %s, NULL, 'In Process', 'Pedido Simulado Incrementador', %s)
            """
            cursor.execute(
                insert_order_query, (order_num, order_date, required_date, customer_num)
            )

            # Inserir detalhes (pelo menos 1 detalhe, podendo ser até 3)
            num_details = random.randint(1, 3)
            # Garantir produtos distintos para a mesma ordem
            chosen_products = random.sample(products, num_details)

            for line_idx, prod in enumerate(chosen_products, start=1):
                prod_code, prod_msrp = prod
                qty_ordered = random.randint(5, 50)
                # O preço unitário pode ter uma variação pequena em torno do MSRP para ser realista
                price_each = round(float(prod_msrp) * random.uniform(0.9, 1.0), 2)

                insert_detail_query = """
                INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(
                    insert_detail_query,
                    (order_num, prod_code, qty_ordered, price_each, line_idx),
                )
                total_details_count += 1

            simulated_orders.append(order_num)

        conn.commit()

        # 5. Imprimir resumo
        logger.info("\n=== RESUMO DA SIMULAÇÃO ===")
        logger.info(f"Pedidos criados: {simulated_orders}")
        logger.info(f"Quantidade total de pedidos: {len(simulated_orders)}")
        logger.info(f"Faixa de datas: {min_simulated_date} até {max_simulated_date}")
        logger.info(f"Total de linhas em orderdetails: {total_details_count}")
        logger.info("===========================")

    except Exception as e:
        logger.error(f"Erro durante a simulação: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    main()
