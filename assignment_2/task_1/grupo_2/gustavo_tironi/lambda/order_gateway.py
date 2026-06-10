"""
Lambda gateway: valida pedidos simulados antes de inserir no RDS.

Verificações (todas devem passar para inserir):
  1. len(details) >= 1
  2. customerNumber existe em customers
  3. todo productCode em details existe em products
  4. orderDate > etl_watermark.last_processed_order_date (PIPELINE_NAME)
  5. quantityOrdered * priceEach > 0 e consistente (sem valores negativos/zero)

Se passar: insere orders + orderdetails em transação. Rollback no erro.

Event esperado:
{
  "order": {
    "orderNumber": int,
    "orderDate": "YYYY-MM-DD",
    "requiredDate": "YYYY-MM-DD",
    "status": str,
    "comments": str,
    "customerNumber": int
  },
  "details": [
    {"productCode": str, "quantityOrdered": int, "priceEach": float, "orderLineNumber": int},
    ...
  ]
}

Resposta:
  {"status": "ok"|"rejected", "orderNumber": int, "errors": [str, ...]}
"""

import json
import os
from datetime import date, datetime

import boto3
import mysql.connector

SECRET_ARN = os.environ["SECRET_ARN"]
DB_NAME = os.environ.get("DB_NAME", "classicmodels")
REGION = os.environ.get("AWS_REGION", "us-east-1")
PIPELINE_NAME = os.environ.get("PIPELINE_NAME", "classicmodels_sales")


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


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def validate(cur, event: dict) -> list[str]:
    """Validações em memória + lookups no RDS (read-only, antes do INSERT)."""
    errors = []
    order = event.get("order") or {}
    details = event.get("details") or []

    # 1. ao menos 1 linha de detalhe
    if len(details) < 1:
        errors.append("orderdetails vazio: ao menos 1 linha exigida")

    # 5. métricas consistentes
    for i, d in enumerate(details):
        q = d.get("quantityOrdered")
        p = d.get("priceEach")
        if q is None or p is None:
            errors.append(f"details[{i}]: quantityOrdered/priceEach ausente")
            continue
        if q <= 0:
            errors.append(f"details[{i}]: quantityOrdered={q} inválido (deve ser > 0)")
        if p <= 0:
            errors.append(f"details[{i}]: priceEach={p} inválido (deve ser > 0)")

    # 2. customerNumber existe
    customer_number = order.get("customerNumber")
    if customer_number is None:
        errors.append("customerNumber ausente")
    else:
        cur.execute(
            "SELECT 1 FROM customers WHERE customerNumber = %s",
            (customer_number,),
        )
        if cur.fetchone() is None:
            errors.append(f"customerNumber={customer_number} não existe em customers")

    # 3. todo productCode existe
    product_codes = [d.get("productCode") for d in details if d.get("productCode")]
    if product_codes:
        placeholders = ",".join(["%s"] * len(product_codes))
        cur.execute(
            f"SELECT productCode FROM products WHERE productCode IN ({placeholders})",
            tuple(product_codes),
        )
        found = {row[0] for row in cur.fetchall()}
        missing = set(product_codes) - found
        for code in missing:
            errors.append(f"productCode={code} não existe em products")

    # 4. orderDate > watermark
    order_date = _parse_date(order.get("orderDate"))
    if order_date is None:
        errors.append("orderDate ausente ou em formato inválido (esperado YYYY-MM-DD)")
    else:
        cur.execute(
            "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
            (PIPELINE_NAME,),
        )
        row = cur.fetchone()
        if row is None:
            errors.append(f"etl_watermark sem registro para pipeline '{PIPELINE_NAME}'")
        else:
            watermark = row[0]
            if watermark is not None and order_date <= watermark:
                errors.append(
                    f"orderDate={order_date} deve ser estritamente posterior ao watermark={watermark}"
                )

    return errors


def lambda_handler(event, context):
    order_number = event.get("order", {}).get("orderNumber")

    conn = None
    try:
        secret = get_secret()
        conn = connect(secret)
        cur = conn.cursor()

        errors = validate(cur, event)
        if errors:
            return {"status": "rejected", "orderNumber": order_number, "errors": errors}

        order = event["order"]
        details = event["details"]

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
                order.get("comments"),
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
        cur.close()
        return {"status": "ok", "orderNumber": order_number, "errors": []}

    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return {"status": "rejected", "orderNumber": order_number, "errors": [str(exc)]}
    finally:
        if conn is not None and conn.is_connected():
            conn.close()
