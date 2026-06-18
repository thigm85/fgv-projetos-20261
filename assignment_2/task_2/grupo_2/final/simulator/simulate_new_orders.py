"""
Simula chegada de novos pedidos no banco classicmodels.

Uso:
    python simulate_new_orders.py [--count N] [--seed S] [--via-lambda]

- Escolhe customerNumber e productCode existentes aleatoriamente.
- Insere em orders com orderDate estritamente posterior ao watermark atual
  (ou MAX(orders.orderDate), o que for maior).
- Insere ao menos uma linha em orderdetails por pedido.
- NÃO atualiza etl_watermark (responsabilidade do job Glue na Task 2).
- orderNumber calculado como MAX(orderNumber) + incremento sequencial
  (o schema do classicmodels não usa AUTO_INCREMENT nessa coluna).

Modos de inserção:
  - default: INSERT direto no RDS (transação local).
  - --via-lambda: payload enviado para a Lambda gateway, que valida e insere.

Exit code: 0 = sucesso, 1 = falha.
"""

import argparse
import json
import logging
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import boto3
import mysql.connector

# Permite rodar de qualquer diretório, carregando src/.env
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import envlocal

envlocal.load()

SECRET_ARN = os.environ["SECRET_ARN"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
DB_NAME = "classicmodels"
PIPELINE_NAME = "classicmodels_sales"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("simulate_new_orders")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simula novos pedidos no classicmodels")
    p.add_argument("--count", type=int, default=5, help="Número de pedidos a criar (default: 5)")
    p.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade")
    p.add_argument(
        "--via-lambda",
        action="store_true",
        help="Envia pedidos para Lambda gateway (valida antes de inserir).",
    )
    return p.parse_args()


def get_secret() -> dict:
    client = boto3.client("secretsmanager", region_name=REGION)
    return json.loads(client.get_secret_value(SecretId=SECRET_ARN)["SecretString"])


def connect(secret: dict):
    return mysql.connector.connect(
        host=secret["host"],
        user=secret["username"],
        password=secret["password"],
        port=int(secret["port"]),
        database=DB_NAME,
        use_pure=True,
        connection_timeout=10,
        autocommit=False,
    )


def get_watermark_date(cur) -> date | None:
    cur.execute(
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_max_order_date(cur) -> date | None:
    cur.execute("SELECT MAX(orderDate) FROM orders")
    row = cur.fetchone()
    return row[0] if row else None


def next_weekday(d: date) -> date:
    """Próximo dia útil após `d` (pula sábado e domingo)."""
    d = d + timedelta(days=1)
    while d.weekday() >= 5:  # 5=sábado, 6=domingo
        d = d + timedelta(days=1)
    return d


def get_baseline_date(cur) -> date:
    """
    Retorna a maior data entre:
      - watermark
      - MAX(orderDate)
      - hoje - 30 dias (força datas recentes para testes de partição na Task 2)
    """
    wm = get_watermark_date(cur)
    max_date = get_max_order_date(cur)
    recent_floor = date.today() - timedelta(days=30)

    candidates = [d for d in [wm, max_date, recent_floor] if d is not None]
    return max(candidates)


def get_customers(cur) -> list[int]:
    cur.execute("SELECT customerNumber FROM customers")
    return [row[0] for row in cur.fetchall()]


def get_products(cur) -> list[str]:
    cur.execute("SELECT productCode FROM products")
    return [row[0] for row in cur.fetchall()]


def get_product_price(cur, product_code: str) -> float:
    cur.execute("SELECT MSRP FROM products WHERE productCode = %s", (product_code,))
    row = cur.fetchone()
    return float(row[0]) if row else 10.0


def get_next_order_number(cur) -> int:
    cur.execute("SELECT MAX(orderNumber) FROM orders")
    return (cur.fetchone()[0] or 0) + 1


def build_payloads(cur, rng: random.Random, count: int) -> list[dict]:
    """Gera os payloads dos pedidos (leituras read-only no RDS para escolher IDs válidos)."""
    baseline = get_baseline_date(cur)
    log.info("Data de referência (baseline): %s", baseline)

    customers = get_customers(cur)
    products = get_products(cur)

    if not customers or not products:
        raise RuntimeError("Banco sem customers ou products — verifique a carga inicial")

    next_order_number = get_next_order_number(cur)
    payloads = []
    order_date = baseline

    for i in range(count):
        order_number = next_order_number + i
        order_date = next_weekday(order_date)
        required_date = order_date + timedelta(days=7)
        if required_date.weekday() >= 5:
            required_date = next_weekday(required_date)
        customer = rng.choice(customers)

        num_lines = rng.randint(1, 3)
        chosen_products = rng.sample(products, min(num_lines, len(products)))
        details = []
        for line_num, product_code in enumerate(chosen_products, start=1):
            price = get_product_price(cur, product_code)
            price_each = round(price * rng.uniform(0.70, 1.00), 2)
            details.append({
                "productCode": product_code,
                "quantityOrdered": rng.randint(1, 20),
                "priceEach": price_each,
                "orderLineNumber": line_num,
            })

        payloads.append({
            "order": {
                "orderNumber": order_number,
                "orderDate": order_date.isoformat(),
                "requiredDate": required_date.isoformat(),
                "status": "In Process",
                "comments": f"Pedido simulado A2/Task1 #{i+1}",
                "customerNumber": customer,
            },
            "details": details,
        })

    return payloads


def insert_direct(conn, payload: dict) -> tuple[bool, str | None]:
    """Insere direto no RDS em transação. Retorna (ok, erro)."""
    cur = conn.cursor()
    order = payload["order"]
    details = payload["details"]
    try:
        cur.execute(
            """
            INSERT INTO orders
                (orderNumber, orderDate, requiredDate, shippedDate, status, comments, customerNumber)
            VALUES (%s, %s, %s, NULL, %s, %s, %s)
            """,
            (
                order["orderNumber"],
                order["orderDate"],
                order["requiredDate"],
                order["status"],
                order["comments"],
                order["customerNumber"],
            ),
        )
        for d in details:
            cur.execute(
                """
                INSERT INTO orderdetails
                    (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    order["orderNumber"],
                    d["productCode"],
                    d["quantityOrdered"],
                    d["priceEach"],
                    d["orderLineNumber"],
                ),
            )
        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        cur.close()


def insert_via_lambda(lambda_client, function_name: str, payload: dict) -> tuple[bool, str | None]:
    """Envia payload para Lambda gateway. Retorna (ok, erro)."""
    resp = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps(payload).encode("utf-8"),
    )
    body = json.loads(resp["Payload"].read())
    if body.get("status") == "ok":
        return True, None
    return False, "; ".join(body.get("errors") or ["erro desconhecido"])


def simulate(conn, rng: random.Random, count: int, via_lambda: bool) -> list[dict]:
    cur = conn.cursor()
    payloads = build_payloads(cur, rng, count)
    cur.close()

    lambda_client = None
    function_name = None
    if via_lambda:
        function_name = os.environ.get("LAMBDA_ORDER_GATEWAY")
        if not function_name:
            raise RuntimeError("LAMBDA_ORDER_GATEWAY não definido no .env")
        lambda_client = boto3.client("lambda", region_name=REGION)
        log.info("Modo: via Lambda gateway (%s)", function_name)
    else:
        log.info("Modo: INSERT direto no RDS")

    created = []
    for p in payloads:
        order = p["order"]
        if via_lambda:
            ok, err = insert_via_lambda(lambda_client, function_name, p)
        else:
            ok, err = insert_direct(conn, p)

        if not ok:
            log.error("  [REJECTED] orderNumber=%d: %s", order["orderNumber"], err)
            continue

        created.append({
            "order_number": order["orderNumber"],
            "order_date": order["orderDate"],
            "customer": order["customerNumber"],
            "detail_lines": len(p["details"]),
        })
        log.info(
            "  [ok] orderNumber=%d date=%s customerNumber=%d details=%d",
            order["orderNumber"], order["orderDate"], order["customerNumber"], len(p["details"]),
        )

    return created


def print_summary(created: list[dict]) -> None:
    if not created:
        log.info("Nenhum pedido criado.")
        return

    dates = [o["order_date"] for o in created]
    total_details = sum(o["detail_lines"] for o in created)
    order_ids = [o["order_number"] for o in created]

    log.info("=" * 50)
    log.info("RESUMO")
    log.info("  Pedidos criados: %d", len(created))
    log.info("  IDs: %s", order_ids)
    log.info("  Faixa de datas: %s → %s", min(dates), max(dates))
    log.info("  Total linhas em orderdetails: %d", total_details)
    log.info("=" * 50)


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    conn = None
    try:
        secret = get_secret()
        conn = connect(secret)
        created = simulate(conn, rng, args.count, args.via_lambda)
        print_summary(created)
        return 0
    except Exception as exc:
        log.exception("Falha: %s", exc)
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return 1
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
