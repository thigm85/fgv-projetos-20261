#!/usr/bin/env python3
"""
Simula chegada de novos pedidos no banco classicmodels.

Uso:
    python scripts/simulate_new_orders.py [--count N] [--seed S] [--dry-run]

Comportamento:
  - Escolhe customerNumber e productCode existentes no banco.
  - Insere em orders com orderDate estritamente posterior ao watermark atual
    (ou MAX(orders.orderDate), o que for maior).
  - Insere ao menos uma linha em orderdetails por pedido.
  - priceEach entre buyPrice e MSRP (regra de negócio do star schema).
  - Garante quantityOrdered * priceEach > 0 (consistência com sales_amount do A1).
  - NÃO atualiza etl_watermark (responsabilidade do job Glue na Task 2).
  - Usa transações para garantir atomicidade (orders + orderdetails juntos).
  - orderNumber calculado como MAX(orderNumber) + incremento sequencial
    (o schema do classicmodels não usa AUTO_INCREMENT nessa coluna).

Features consolidadas de:
  - Matheus: dry-run, status variados, shippedDate, FOR UPDATE, tabela formatada
  - Alessandra: priceEach entre buyPrice e MSRP
  - Gustavo: baseline com dias úteis recentes
  - Sillas: bootstrap de referências

Exit code: 0 = sucesso, 1 = falha.
"""

import argparse
import logging
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Adiciona o diretório pai ao path para importar db_config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db_config

PIPELINE_NAME = "classicmodels_sales"

# Distribuição de status dos pedidos simulados (Matheus)
STATUS_WEIGHTS = [
    ("In Process", 60),
    ("Shipped", 30),
    ("On Hold", 10),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("simulate_new_orders")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Simula novos pedidos no banco classicmodels (Assignment 2 — Task 1)"
    )
    p.add_argument(
        "--count", type=int, default=5,
        help="Número de pedidos a criar (default: 5)"
    )
    p.add_argument(
        "--seed", type=int, default=None,
        help="Seed para reprodutibilidade de demos"
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Mostra os pedidos que seriam criados sem inserir no banco"
    )
    return p.parse_args()


# ── Funções auxiliares ────────────────────────────────────────────────────────

def next_weekday(d: date) -> date:
    """Retorna o próximo dia útil estritamente após `d`."""
    d = d + timedelta(days=1)
    while d.weekday() >= 5:  # 5=sábado, 6=domingo
        d = d + timedelta(days=1)
    return d


def pick_status(rng: random.Random) -> str:
    """Escolhe status aleatório com pesos definidos."""
    statuses, weights = zip(*STATUS_WEIGHTS)
    return rng.choices(statuses, weights=weights, k=1)[0]


def get_watermark_date(cur) -> date | None:
    """Lê last_processed_order_date do watermark (pode ser None se tabela não existir)."""
    try:
        cur.execute(
            "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
            (PIPELINE_NAME,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def get_max_order_date(cur) -> date | None:
    """Retorna MAX(orderDate) da tabela orders."""
    cur.execute("SELECT MAX(orderDate) FROM orders")
    row = cur.fetchone()
    return row[0] if row else None


def get_baseline_date(cur) -> date:
    """
    Retorna a maior data entre watermark, MAX(orderDate) e (hoje - 30 dias).
    Força datas recentes para facilitar testes de partição na Task 2.
    """
    wm = get_watermark_date(cur)
    max_date = get_max_order_date(cur)
    recent_floor = date.today() - timedelta(days=30)

    candidates = [d for d in [wm, max_date, recent_floor] if d is not None]
    if not candidates:
        return date.today()
    return max(candidates)


def get_customers(cur) -> list[int]:
    """Retorna todos os customerNumbers existentes."""
    cur.execute("SELECT customerNumber FROM customers")
    return [row[0] for row in cur.fetchall()]


def get_products(cur) -> list[tuple[str, float, float]]:
    """Retorna todos os (productCode, buyPrice, MSRP) existentes."""
    cur.execute("SELECT productCode, buyPrice, MSRP FROM products")
    return [(row[0], float(row[1]), float(row[2])) for row in cur.fetchall()]


def get_next_order_number(cur) -> int:
    """
    Obtém o próximo orderNumber disponível.
    Usa FOR UPDATE para evitar colisão em execuções concorrentes.
    """
    cur.execute("SELECT MAX(orderNumber) FROM orders FOR UPDATE")
    max_num = cur.fetchone()[0]
    return (max_num or 0) + 1


# ── Geração de payloads ──────────────────────────────────────────────────────

def build_order_payloads(
    cur, rng: random.Random, count: int
) -> list[dict]:
    """
    Gera payloads dos pedidos com dados coerentes.
    Leituras read-only no RDS para escolher IDs válidos.
    """
    baseline = get_baseline_date(cur)
    log.info("Data de referência (baseline): %s", baseline)

    customers = get_customers(cur)
    products = get_products(cur)

    if not customers:
        raise RuntimeError("Tabela 'customers' vazia — verifique a carga inicial do A1.")
    if not products:
        raise RuntimeError("Tabela 'products' vazia — verifique a carga inicial do A1.")

    log.info("Pool: %d clientes, %d produtos disponíveis", len(customers), len(products))

    # Obtém próximo orderNumber (FOR UPDATE para concorrência)
    next_order_num = get_next_order_number(cur)

    payloads = []
    order_date = baseline

    for i in range(count):
        order_number = next_order_num + i
        order_date = next_weekday(order_date)

        # requiredDate: 7 a 14 dias úteis após orderDate
        req_offset = rng.randint(7, 14)
        required_date = order_date + timedelta(days=req_offset)
        if required_date.weekday() >= 5:
            required_date = next_weekday(required_date)

        customer = rng.choice(customers)
        status = pick_status(rng)

        # shippedDate: apenas para pedidos Shipped (entre orderDate e requiredDate)
        shipped_date = None
        if status == "Shipped":
            days_to_ship = rng.randint(1, (required_date - order_date).days or 1)
            shipped_date = order_date + timedelta(days=days_to_ship)

        # Gera 1 a 4 linhas de detalhe
        num_lines = rng.randint(1, min(4, len(products)))
        chosen_products = rng.sample(products, num_lines)

        details = []
        for line_num, (product_code, buy_price, msrp) in enumerate(chosen_products, start=1):
            quantity = rng.randint(1, 50)
            # Preço entre buyPrice e MSRP — regra de negócio do star schema (Alessandra)
            price_each = round(rng.uniform(buy_price, msrp), 2)
            price_each = max(price_each, 0.01)  # failsafe

            details.append({
                "productCode": product_code,
                "quantityOrdered": quantity,
                "priceEach": price_each,
                "orderLineNumber": line_num,
            })

        payloads.append({
            "order": {
                "orderNumber": order_number,
                "orderDate": order_date,
                "requiredDate": required_date,
                "shippedDate": shipped_date,
                "status": status,
                "comments": f"Pedido simulado A2/Task1 #{i + 1}",
                "customerNumber": customer,
            },
            "details": details,
        })

    return payloads


# ── Inserção ──────────────────────────────────────────────────────────────────

def insert_order(conn, payload: dict) -> None:
    """
    Insere um pedido (order + orderdetails) dentro da transação ativa.
    Em caso de erro, faz rollback e relança a exceção.
    """
    cur = conn.cursor()
    order = payload["order"]
    details = payload["details"]

    try:
        cur.execute(
            """
            INSERT INTO orders
                (orderNumber, orderDate, requiredDate, shippedDate,
                 status, comments, customerNumber)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                order["orderNumber"],
                order["orderDate"],
                order["requiredDate"],
                order["shippedDate"],
                order["status"],
                order["comments"],
                order["customerNumber"],
            ),
        )

        for d in details:
            # Validação interna antes do INSERT
            assert d["quantityOrdered"] > 0, f"quantityOrdered inválido: {d['quantityOrdered']}"
            assert d["priceEach"] > 0, f"priceEach inválido: {d['priceEach']}"

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
    finally:
        cur.close()


# ── Resumo ────────────────────────────────────────────────────────────────────

def print_summary(created: list[dict], dry_run: bool = False) -> None:
    """Imprime tabela formatada com resumo dos pedidos criados/previstos."""
    mode = "SIMULAÇÃO (dry-run)" if dry_run else "CRIADOS"

    if not created:
        log.info("Nenhum pedido %s.", "previsto" if dry_run else "criado")
        return

    # Cabeçalho
    log.info("")
    log.info("=" * 80)
    log.info("RESUMO — Pedidos %s", mode)
    log.info("=" * 80)

    # Tabela
    header = (
        f"  {'#':<4} {'orderNumber':<13} {'orderDate':<12} "
        f"{'status':<13} {'customer':<10} {'details':<8} {'sales_amount':>13}"
    )
    log.info(header)
    log.info("  " + "-" * 76)

    total_details = 0
    total_amount = 0.0
    dates = []

    for idx, order in enumerate(created, 1):
        sales = sum(d["quantityOrdered"] * d["priceEach"] for d in order["details"])
        n_details = len(order["details"])
        total_details += n_details
        total_amount += sales
        dates.append(order["order"]["orderDate"])

        log.info(
            "  %-4d %-13d %-12s %-13s %-10d %-8d %13.2f",
            idx,
            order["order"]["orderNumber"],
            order["order"]["orderDate"],
            order["order"]["status"],
            order["order"]["customerNumber"],
            n_details,
            sales,
        )

    log.info("  " + "-" * 76)
    log.info("  Pedidos: %d", len(created))
    log.info("  Faixa de datas: %s → %s", min(dates), max(dates))
    log.info("  Total linhas em orderdetails: %d", total_details)
    log.info("  Sales amount total: %.2f", total_amount)
    log.info("  IDs: %s", [o["order"]["orderNumber"] for o in created])
    log.info("=" * 80)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    if args.count <= 0:
        log.error("--count deve ser > 0 (recebido: %d)", args.count)
        return 1

    conn = None
    try:
        conn = db_config.get_connection(autocommit=False)
        cur = conn.cursor()

        log.info("Gerando %d pedido(s)%s...", args.count, " (dry-run)" if args.dry_run else "")

        payloads = build_order_payloads(cur, rng, args.count)
        cur.close()

        if args.dry_run:
            log.info("Modo dry-run — nenhum dado será inserido no banco.")
            print_summary(payloads, dry_run=True)
            return 0

        # Insere cada pedido em transação
        created = []
        for p in payloads:
            try:
                insert_order(conn, p)
                conn.commit()
                created.append(p)
                log.info(
                    "  ✓ orderNumber=%d date=%s status=%s customer=%d details=%d",
                    p["order"]["orderNumber"],
                    p["order"]["orderDate"],
                    p["order"]["status"],
                    p["order"]["customerNumber"],
                    len(p["details"]),
                )
            except Exception as exc:
                conn.rollback()
                log.error(
                    "  ✗ orderNumber=%d FALHOU: %s",
                    p["order"]["orderNumber"],
                    exc,
                )

        print_summary(created)

        if len(created) < len(payloads):
            log.warning(
                "%d de %d pedidos falharam.",
                len(payloads) - len(created),
                len(payloads),
            )
            return 1

        return 0

    except Exception as exc:
        log.exception("Falha na simulação: %s", exc)
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
