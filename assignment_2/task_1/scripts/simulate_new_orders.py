"""
Task 1 (3.2) — Simula a chegada de novos pedidos no OLTP (classicmodels).

Para cada pedido simulado:
  - Escolhe customerNumber e productCode(s) EXISTENTES no banco.
  - Insere em orders com orderDate estritamente posterior ao watermark / MAX(orderDate).
  - Insere >= 1 linha em orderdetails coerente (quantityOrdered, priceEach, orderLineNumber).
  - priceEach derivado de products.MSRP, mantendo sales_amount = quantity * priceEach (regra do A1).

NÃO atualiza etl_watermark (3.2.3) — isso é responsabilidade do job Glue na Task 2.

Gotcha tratado: orders.orderNumber NÃO é AUTO_INCREMENT neste dump, então o próximo id é
calculado via MAX(orderNumber)+1 e incrementado em memória dentro da transação.

Uso:
  python simulate_new_orders.py --count 5 --seed 42
  python simulate_new_orders.py --count 10 --min-lines 1 --max-lines 4
"""
import argparse
import random
import sys
from datetime import date, timedelta

from db import load_config, connect_with_retry

PIPELINE_NAME = "classicmodels_sales"
TODAY = date(2026, 6, 6)  # data de referência do laboratório


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simula novos pedidos no OLTP classicmodels.")
    p.add_argument("--count", type=int, default=5, help="Número de pedidos a criar (default: 5).")
    p.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade (opcional).")
    p.add_argument("--min-lines", type=int, default=1, help="Mín. de linhas por pedido (default: 1).")
    p.add_argument("--max-lines", type=int, default=4, help="Máx. de linhas por pedido (default: 4).")
    return p.parse_args()


def business_days_ending(end: date, n: int) -> list:
    """Retorna n dias úteis (seg-sex) em ordem crescente, terminando em/antes de `end`."""
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:  # 0=segunda ... 4=sexta
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def fetch_reference_data(cur):
    """Lê watermark, ids existentes e o máximo de orderNumber/orderDate."""
    cur.execute(
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "Watermark 'classicmodels_sales' não encontrado. Rode init_watermark.py primeiro."
        )
    watermark = row[0]

    cur.execute("SELECT MAX(orderNumber), MAX(orderDate) FROM orders")
    max_order_number, max_order_date = cur.fetchone()

    cur.execute("SELECT customerNumber FROM customers")
    customers = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT productCode, MSRP FROM products")
    products = [(r[0], float(r[1])) for r in cur.fetchall()]

    return watermark, max_order_number, max_order_date, customers, products


def simulate(conn, count: int, min_lines: int, max_lines: int) -> dict:
    created_orders = []
    total_detail_rows = 0

    with conn.cursor() as cur:
        watermark, max_order_number, max_order_date, customers, products = fetch_reference_data(cur)

        # Datas: dias úteis recentes até hoje, garantindo > watermark e > MAX(orderDate).
        floor_date = max(d for d in [watermark, max_order_date] if d is not None)
        start_after = max(floor_date, TODAY - timedelta(days=1))
        if start_after >= TODAY:
            # histórico já alcança/passa hoje: gerar dias úteis logo após o piso
            order_dates = []
            d = floor_date + timedelta(days=1)
            while len(order_dates) < count:
                if d.weekday() < 5:
                    order_dates.append(d)
                d += timedelta(days=1)
        else:
            order_dates = business_days_ending(TODAY, count)

        next_order_number = (max_order_number or 0) + 1

        for i in range(count):
            order_number = next_order_number + i
            order_date = order_dates[i % len(order_dates)]
            required_date = order_date + timedelta(days=7)
            customer = random.choice(customers)

            cur.execute(
                "INSERT INTO orders "
                "(orderNumber, orderDate, requiredDate, shippedDate, status, comments, customerNumber) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (order_number, order_date, required_date, None, "Shipped",
                 "Simulated incremental order", customer),
            )

            # productCodes DISTINTOS (PK composta orderNumber+productCode)
            n_lines = random.randint(min_lines, min(max_lines, len(products)))
            chosen = random.sample(products, n_lines)
            for line_no, (product_code, msrp) in enumerate(chosen, start=1):
                quantity = random.randint(1, 50)
                # priceEach realista: ~85-100% do MSRP, 2 casas
                price_each = round(msrp * random.uniform(0.85, 1.00), 2)
                cur.execute(
                    "INSERT INTO orderdetails "
                    "(orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (order_number, product_code, quantity, price_each, line_no),
                )
                total_detail_rows += 1

            created_orders.append((order_number, order_date, n_lines))

    return {
        "watermark": watermark,
        "orders": created_orders,
        "total_detail_rows": total_detail_rows,
    }


def main() -> int:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    print("=" * 60)
    print("Task 1 (3.2) — Simulação de novos pedidos")
    print("=" * 60)
    print(f"count={args.count}  seed={args.seed}  lines={args.min_lines}-{args.max_lines}")

    cfg = load_config()
    conn = None
    try:
        conn = connect_with_retry(cfg)
        result = simulate(conn, args.count, args.min_lines, args.max_lines)
        conn.commit()
        print("\n  Transação commitada.")
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"\n[ERRO] {exc} — rollback realizado (nenhum pedido inserido).")
        return 1
    finally:
        if conn:
            conn.close()
            print("  Conexão encerrada.")

    # Resumo (3.2.4)
    orders = result["orders"]
    order_ids = [o[0] for o in orders]
    dates = sorted(o[1] for o in orders)
    print("\n" + "-" * 60)
    print("Resumo da simulação")
    print("-" * 60)
    print(f"  Watermark atual         : {result['watermark']}")
    print(f"  Pedidos criados ({len(orders)})    : {order_ids}")
    print(f"  Faixa de datas          : {dates[0]} .. {dates[-1]}")
    print(f"  Linhas em orderdetails  : {result['total_detail_rows']}")
    print("\n  (etl_watermark NÃO foi alterado — isso é responsabilidade da Task 2.)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
