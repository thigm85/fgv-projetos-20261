import argparse
import logging
import random
import sys
from datetime import date, timedelta

from config import Settings, load_settings
from db import connect_mysql


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def next_business_day(reference: date) -> date:
    """Retorna o próximo dia útil (pula sábado/domingo) após `reference`."""

    candidate = reference + timedelta(days=1)
    while candidate.weekday() >= 5:  # 5 = sábado, 6 = domingo
        candidate += timedelta(days=1)
    return candidate


def fetch_baseline_date(cursor, pipeline_name: str) -> date:
    cursor.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
    max_order_date = cursor.fetchone()["max_order_date"]

    cursor.execute(
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (pipeline_name,),
    )
    wm_row = cursor.fetchone()
    watermark_date = wm_row["last_processed_order_date"] if wm_row else None

    candidates = [d for d in (max_order_date, watermark_date) if d is not None]
    if not candidates:
        raise RuntimeError(
            "Não há pedidos nem watermark: carregue o banco e rode init_watermark antes."
        )
    return max(candidates)


def fetch_next_order_number(cursor) -> int:
    cursor.execute("SELECT COALESCE(MAX(orderNumber), 10099) AS max_order FROM orders")
    return int(cursor.fetchone()["max_order"]) + 1


def fetch_customers(cursor) -> list[int]:
    cursor.execute("SELECT customerNumber FROM customers")
    return [int(row["customerNumber"]) for row in cursor.fetchall()]


def fetch_products(cursor) -> list[dict]:
    cursor.execute("SELECT productCode, MSRP FROM products")
    return [
        {"productCode": row["productCode"], "price": float(row["MSRP"])}
        for row in cursor.fetchall()
    ]


def run_simulation(settings: Settings, args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)
    conn = None

    try:
        conn = connect_mysql(settings)
        conn.autocommit(False)

        created_orders: list[int] = []
        order_dates: list[date] = []
        total_detail_lines = 0

        with conn.cursor() as cursor:
            baseline = fetch_baseline_date(cursor, settings.pipeline_name)
            next_order = fetch_next_order_number(cursor)
            customers = fetch_customers(cursor)
            products = fetch_products(cursor)

            if not customers or not products:
                raise RuntimeError("customers/products vazios: carregue o banco primeiro.")

            logger.info("Baseline (watermark/MAX orderDate): %s", baseline)
            logger.info("Próximo orderNumber: %s", next_order)

            current_date = baseline
            for index in range(args.count):
                current_date = next_business_day(current_date)
                order_number = next_order + index
                customer_number = rng.choice(customers)

                required_date = current_date + timedelta(days=7)
                shipped_date = current_date + timedelta(days=3)

                cursor.execute(
                    """
                    INSERT INTO orders (
                        orderNumber, orderDate, requiredDate, shippedDate,
                        status, comments, customerNumber
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        order_number,
                        current_date,
                        required_date,
                        shipped_date,
                        "Shipped",
                        "Pedido simulado (Assignment 2 - Task 1)",
                        customer_number,
                    ),
                )

                line_count = rng.randint(args.min_lines, args.max_lines)
                chosen_products = rng.sample(products, k=min(line_count, len(products)))

                for line_number, product in enumerate(chosen_products, start=1):
                    quantity = rng.randint(10, 80)
                    price_each = round(product["price"], 2)

                    cursor.execute(
                        """
                        INSERT INTO orderdetails (
                            orderNumber, productCode, quantityOrdered,
                            priceEach, orderLineNumber
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            order_number,
                            product["productCode"],
                            quantity,
                            price_each,
                            line_number,
                        ),
                    )
                    total_detail_lines += 1

                created_orders.append(order_number)
                order_dates.append(current_date)

        conn.commit()

        logger.info("=" * 60)
        logger.info("RESUMO DA SIMULAÇÃO")
        logger.info("Pedidos criados (%s): %s", len(created_orders), created_orders)
        logger.info(
            "Faixa de datas: %s a %s",
            min(order_dates).isoformat(),
            max(order_dates).isoformat(),
        )
        logger.info("Linhas inseridas em orderdetails: %s", total_detail_lines)
        logger.info("=" * 60)
        logger.info(
            "Watermark NÃO foi alterado (responsabilidade do job Glue na Task 2)."
        )
        return 0

    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Falha na simulação. Rollback executado (nenhum pedido criado).")
        return 1

    finally:
        if conn and conn.open:
            conn.close()
            logger.info("Conexão encerrada")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simula novos pedidos no OLTP classicmodels para teste de carga incremental"
    )
    parser.add_argument(
        "--count", type=int, default=5, help="Número de pedidos a criar (default: 5)"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Semente para reprodutibilidade de demos"
    )
    parser.add_argument(
        "--min-lines",
        type=int,
        default=1,
        help="Mínimo de linhas em orderdetails por pedido (default: 1)",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=3,
        help="Máximo de linhas em orderdetails por pedido (default: 3)",
    )
    args = parser.parse_args()

    if args.count <= 0:
        parser.error("--count deve ser maior que zero")
    if args.min_lines <= 0 or args.max_lines < args.min_lines:
        parser.error("--min-lines/--max-lines inválidos")
    return args


def main() -> int:
    try:
        settings = load_settings()
        return run_simulation(settings, parse_args())
    except Exception:
        logger.exception("Erro fatal na simulação")
        return 1


if __name__ == "__main__":
    sys.exit(main())
