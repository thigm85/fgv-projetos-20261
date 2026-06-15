#!/usr/bin/env python3
"""
Print Evidências (README §3.4) for manual copy-paste.

Run BEFORE the 2nd demo/Glue cycle (after simulate, before Glue):
    python scripts/print_evidence.py before

Run AFTER the 2nd Glue job finishes:
    python scripts/print_evidence.py after

Optional — Terraform/trigger reference for §3.4.3:
    python scripts/print_evidence.py schedule
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = ROOT / "terraform"
TASK1_ROOT = ROOT.parents[2] / "task_1" / "grupo_4" / "aluno_kaiky"

PIPELINE_NAME = "classicmodels_sales"
WATERMARK_TABLE = "etl_watermark"
SALES_TOLERANCE = Decimal("0.01")


def _banner(title: str) -> None:
    line = "=" * 78
    print(line)
    print(title)
    print(f"Gerado em (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    print(line)
    print()


def _section(title: str) -> None:
    print(f"--- {title} ---")


def _terraform_output(name: str) -> str:
    result = subprocess.run(
        ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-raw", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _task1_db():
    sys.path.insert(0, str(TASK1_ROOT))
    from utils.config import load_settings
    from utils.database import db_session, fetch_one

    return load_settings(), db_session, fetch_one


def _watermark_row(settings, db_session, fetch_one) -> dict | None:
    sql = (
        f"SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status "
        f"FROM {WATERMARK_TABLE} WHERE pipeline_name = %s"
    )
    with db_session(settings) as conn:
        return fetch_one(conn, sql, (PIPELINE_NAME,))


def _pending_counts(settings, db_session, fetch_one, watermark_date) -> tuple[int, int]:
    if watermark_date is None:
        return 0, 0

    date_str = (
        watermark_date.strftime("%Y-%m-%d")
        if hasattr(watermark_date, "strftime")
        else str(watermark_date)[:10]
    )
    orders_sql = "SELECT COUNT(*) AS cnt FROM orders WHERE orderDate > DATE(%s)"
    lines_sql = (
        "SELECT COUNT(*) AS cnt FROM orderdetails od "
        "JOIN orders o ON o.orderNumber = od.orderNumber "
        "WHERE o.orderDate > DATE(%s)"
    )
    with db_session(settings) as conn:
        orders = fetch_one(conn, orders_sql, (date_str,)) or {"cnt": 0}
        lines = fetch_one(conn, lines_sql, (date_str,)) or {"cnt": 0}
    return int(orders["cnt"]), int(lines["cnt"])


def _list_fact_s3_keys(s3, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/fact_orders/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet"):
                keys.append(key)
    return keys


def _parquet_row_count(s3, bucket: str, key: str) -> int:
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return pq.read_table(io.BytesIO(body)).num_rows


def _count_fact_rows(s3, bucket: str, prefix: str) -> tuple[int, dict[str, int]]:
    keys = _list_fact_s3_keys(s3, bucket, prefix)
    total = 0
    by_partition: dict[str, int] = {}
    for key in keys:
        rows = _parquet_row_count(s3, bucket, key)
        total += rows
        part = key.split("/fact_orders/", 1)[-1].rsplit("/", 1)[0]
        by_partition[part] = by_partition.get(part, 0) + rows
    return total, by_partition


def _sales_amount_ok(s3, bucket: str, prefix: str) -> bool:
    keys = _list_fact_s3_keys(s3, bucket, prefix)
    if not keys:
        return False
    table = pq.read_table(
        io.BytesIO(s3.get_object(Bucket=bucket, Key=keys[0])["Body"].read())
    )
    qty = table.column("quantity_ordered").to_pylist()
    price = table.column("price_each").to_pylist()
    sales = table.column("sales_amount").to_pylist()
    n = min(table.num_rows, 10_000)
    for i in range(n):
        expected = Decimal(int(qty[i])) * Decimal(str(price[i]))
        got = Decimal(str(sales[i]))
        if abs(got - expected) > SALES_TOLERANCE:
            return False
    return True


def _glue_job_runs(job_name: str, *, limit: int = 5, region: str | None) -> list[dict]:
    glue = boto3.client("glue", region_name=region)
    resp = glue.get_job_runs(JobName=job_name, MaxResults=limit)
    runs = []
    for run in resp.get("JobRuns", []):
        runs.append(
            {
                "Id": run.get("Id"),
                "State": run.get("JobRunState"),
                "StartedOn": str(run.get("StartedOn", "")),
                "CompletedOn": str(run.get("CompletedOn", "")),
                "ErrorMessage": run.get("ErrorMessage"),
            }
        )
    return runs


def _print_watermark(row: dict | None, *, label: str) -> None:
    _section(f"Watermark (RDS) — {label}")
    if not row:
        print("(nenhuma linha em etl_watermark)")
        print()
        return
    print(f"last_processed_order_date: {row['last_processed_order_date']}")
    print(f"last_run_at:                 {row['last_run_at']}")
    print(f"last_run_status:             {row['last_run_status']}")
    print()
    print("SQL de referência:")
    print(
        "SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status"
    )
    print(f"FROM {WATERMARK_TABLE} WHERE pipeline_name = '{PIPELINE_NAME}';")
    print()


def _print_coherence(pending_orders: int, pending_lines: int) -> None:
    _section("Coerência delta → fato (métricas RDS)")
    print(f"Pedidos com orderDate > watermark:      {pending_orders}")
    print(f"Linhas em orderdetails desses pedidos:  {pending_lines}")
    print()


def _print_s3_fact(s3, bucket: str, prefix: str) -> None:
    _section("Partições S3 (fact_orders)")
    paginator = s3.get_paginator("list_objects_v2")
    found = False
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/fact_orders/"):
        for obj in page.get("Contents", []):
            found = True
            print(f"s3://{bucket}/{obj['Key']}")
    if not found:
        print(f"(nenhum objeto em s3://{bucket}/{prefix}/fact_orders/)")
    print()


def _print_glue_runs(job_name: str, *, region: str | None, highlight_latest: bool) -> str | None:
    _section("Glue job runs (recentes)")
    runs = _glue_job_runs(job_name, region=region)
    if not runs:
        print("(nenhum run encontrado)")
        print()
        return None
    latest_id = runs[0]["Id"]
    for i, run in enumerate(runs):
        marker = "  <-- mais recente" if i == 0 and highlight_latest else ""
        print(f"JobRunId: {run['Id']}")
        print(f"  State:      {run['State']}{marker}")
        print(f"  StartedOn:  {run['StartedOn']}")
        if run.get("CompletedOn"):
            print(f"  Completed:  {run['CompletedOn']}")
        if run.get("ErrorMessage"):
            print(f"  Error:      {run['ErrorMessage']}")
        print()
    return latest_id


def _print_terraform_ref() -> tuple[str, str, str, str]:
    _section("Terraform outputs (referência)")
    bucket = _terraform_output("s3_bucket_name")
    prefix = _terraform_output("analytics_prefix")
    job_name = _terraform_output("glue_job_name")
    trigger = _terraform_output("eventbridge_rule_name")
    cron = _terraform_output("eventbridge_schedule")
    db_name = _terraform_output("glue_database_name")
    print(f"s3_bucket_name:        {bucket}")
    print(f"analytics_prefix:      {prefix}")
    print(f"glue_job_name:         {job_name}")
    print(f"eventbridge_rule_name: {trigger}")
    print(f"glue_schedule_cron:    {cron}")
    print(f"glue_database_name:    {db_name}")
    print()
    return bucket, prefix, job_name, trigger


def cmd_before(args: argparse.Namespace) -> int:
    _banner("EVIDÊNCIAS 3.4.2 — ANTES do 2º Glue run")
    print("Copie os valores abaixo para a coluna «Antes do 2º Glue run» no README.")
    print("Execute depois de simulate_new_orders e ANTES de python main.py run-etl / demo.")
    print()

    settings, db_session, fetch_one = _task1_db()
    row = _watermark_row(settings, db_session, fetch_one)
    _print_watermark(row, label='tabela «Antes do 2º Glue run»')

    wm_date = row["last_processed_order_date"] if row else None
    pending_orders, pending_lines = _pending_counts(settings, db_session, fetch_one, wm_date)
    _print_coherence(pending_orders, pending_lines)

    bucket, prefix, job_name, _ = _print_terraform_ref()
    s3 = boto3.client("s3", region_name=args.region)
    _print_s3_fact(s3, bucket, prefix)
    _print_glue_runs(job_name, region=args.region, highlight_latest=False)

    _section("Próximos passos")
    print("1. python scripts/simulate_new_orders.py --count 5   (Task 1, se ainda não simulou)")
    print("2. python scripts/print_evidence.py before          (opcional: conferir pending > 0)")
    print("3. python main.py run-etl  (ou demo)")
    print("4. python scripts/print_evidence.py after")
    print()
    return 0


def cmd_after(args: argparse.Namespace) -> int:
    _banner("EVIDÊNCIAS 3.4.2 — DEPOIS do 2º Glue run")
    print("Copie os valores abaixo para a coluna «Depois do 2º Glue run» no README.")
    print()

    settings, db_session, fetch_one = _task1_db()
    row = _watermark_row(settings, db_session, fetch_one)
    _print_watermark(row, label='tabela «Depois do 2º Glue run»')

    wm_date = row["last_processed_order_date"] if row else None
    pending_orders, pending_lines = _pending_counts(settings, db_session, fetch_one, wm_date)
    _print_coherence(pending_orders, pending_lines)

    bucket, prefix, job_name, _ = _print_terraform_ref()
    s3 = boto3.client("s3", region_name=args.region)

    total_rows, by_part = _count_fact_rows(s3, bucket, prefix)
    _section("fact_orders no S3 (contagem Parquet)")
    print(f"Total de linhas (todos os arquivos .parquet): {total_rows}")
    for part, count in sorted(by_part.items()):
        print(f"  {part}: {count} linha(s)")
    print()
    print("README — «Linhas novas/gravadas em fact_orders»: use a partição tocada neste run.")
    print()

    _print_s3_fact(s3, bucket, prefix)

    latest_id = _print_glue_runs(job_name, region=args.region, highlight_latest=True)
    if latest_id:
        _section("README — Glue JobRunId (2ª execução)")
        print(latest_id)
        print()

    sales_ok = _sales_amount_ok(s3, bucket, prefix) if total_rows else False
    _section("Observações (sugestão para README)")
    incremental_ok = pending_orders == 0 and (row or {}).get("last_run_status") == "SUCCEEDED"
    print(
        f"- Apenas pedidos acima do watermark anterior? "
        f"{'sim' if incremental_ok else 'verificar'} "
        f"(pending_orders={pending_orders}, status={row.get('last_run_status') if row else '?'})"
    )
    print(
        f"- sales_amount = quantity_ordered * price_each? "
        f"{'sim' if sales_ok else 'não / sem dados'}"
    )
    print()

    _section("Athena (consulta sugerida)")
    db = _terraform_output("glue_database_name")
    print(f"SELECT COUNT(*) FROM {db}.fact_orders;")
    if by_part:
        sample = next(iter(sorted(by_part)))
        year = month = "?"
        for token in sample.split("/"):
            if token.startswith("order_year="):
                year = token.split("=", 1)[1]
            if token.startswith("order_month="):
                month = token.split("=", 1)[1]
        print(
            f"SELECT COUNT(*) FROM {db}.fact_orders "
            f"WHERE order_year = {year} AND order_month = {month};"
        )
    print()
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    _banner("EVIDÊNCIAS 3.4.3 — Disparo agendado")
    print("Copie para a tabela §3.4.3 no README.")
    print()

    _, _, job_name, trigger = _print_terraform_ref()
    cron = _terraform_output("eventbridge_schedule")

    _section("Disparo manual do trigger (opcional)")
    print(f"aws glue start-trigger --name {trigger} --region {args.region or 'us-east-1'}")
    print()

    latest_id = _print_glue_runs(job_name, region=args.region, highlight_latest=True)

    _section("README §3.4.3 — campos")
    print(f"eventbridge_rule_name: {trigger}")
    print(f"glue_schedule_cron:    {cron}")
    if latest_id:
        runs = _glue_job_runs(job_name, limit=1, region=args.region)
        if runs:
            print(f"Glue JobRunId:         {runs[0]['Id']}")
            print(f"Estado final:          {runs[0]['State']}")
            print(f"StartedOn (UTC):       {runs[0]['StartedOn']}")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print Evidências README §3.4 for copy-paste (before/after 2nd Glue run)."
    )
    parser.add_argument(
        "phase",
        choices=("before", "after", "schedule"),
        help="before: antes do 2º Glue; after: depois do 2º Glue; schedule: §3.4.3",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region (default: credential chain / AWS_REGION).",
    )
    args = parser.parse_args()

    try:
        if args.phase == "before":
            return cmd_before(args)
        if args.phase == "after":
            return cmd_after(args)
        return cmd_schedule(args)
    except subprocess.CalledProcessError as exc:
        print(f"Terraform/AWS command failed: {exc.stderr or exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
