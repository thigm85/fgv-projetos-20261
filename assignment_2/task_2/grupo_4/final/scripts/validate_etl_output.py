#!/usr/bin/env python3
"""Draft validation for incremental ETL outputs on S3 (pre-Task 3)."""

from __future__ import annotations
import argparse
import io
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
import boto3
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = ROOT / "terraform"

DIM_TABLES = [
    "dim_customers",
    "dim_products",
    "dim_dates",
    "dim_countries",
]

FACT_COLUMNS = {
    "order_id",
    "customer_id",
    "product_id",
    "order_date_key",
    "country_key",
    "quantity_ordered",
    "price_each",
    "sales_amount",
}

SALES_TOLERANCE = Decimal("0.01")


def _terraform_output(name: str) -> str:
    result = subprocess.run(
        ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-raw", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _get_config() -> tuple[str, str]:
    return (
        _terraform_output("s3_bucket_name"),
        _terraform_output("analytics_prefix"),
    )


def _list_parquet_keys(s3, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []

    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=prefix,
    ):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if key.endswith(".parquet"):
                keys.append(key)

    return keys


def _read_parquet(s3, bucket: str, key: str):
    body = s3.get_object(
        Bucket=bucket,
        Key=key,
    )["Body"].read()

    return pq.read_table(io.BytesIO(body))


def _validate_sales(table) -> None:
    qty = table.column("quantity_ordered").to_pylist()
    price = table.column("price_each").to_pylist()
    sales = table.column("sales_amount").to_pylist()

    n = min(table.num_rows, 10_000)

    for i in range(n):
        expected = (
            Decimal(int(qty[i]))
            * Decimal(str(price[i]))
        )
        got = Decimal(str(sales[i]))

        if abs(got - expected) > SALES_TOLERANCE:
            raise ValueError(
                f"sales_amount mismatch row {i}: "
                f"got {got}, expected ~{expected}"
            )


def _validate_dimension_tables(
    s3,
    bucket: str,
    prefix: str,
) -> None:
    for table in DIM_TABLES:
        keys = _list_parquet_keys(
            s3,
            bucket,
            f"{prefix}/{table}/",
        )

        if not keys:
            raise ValueError(
                f"No Parquet found for {table}"
            )

        print(
            f"OK: {table} -> "
            f"s3://{bucket}/{keys[0]}"
        )


def _load_fact_table(
    s3,
    bucket: str,
    prefix: str,
):
    fact_keys = _list_parquet_keys(
        s3,
        bucket,
        f"{prefix}/fact_orders/",
    )

    if not fact_keys:
        raise ValueError(
            "No fact_orders Parquet under partitioned prefix"
        )

    print(
        f"OK: fact_orders "
        f"({len(fact_keys)} parquet file(s))"
    )

    return _read_parquet(
        s3,
        bucket,
        fact_keys[0],
    )


def _validate_fact_schema(table) -> None:
    missing = FACT_COLUMNS - set(table.column_names)

    if missing:
        raise ValueError(
            f"fact_orders missing columns: {missing}"
        )


def _validate_fact_data(table) -> None:
    _validate_sales(table)

    print(
        "OK: sales_amount rule on "
        "fact_orders sample"
    )


def _validate_fact_orders(
    s3,
    bucket: str,
    prefix: str,
) -> None:
    fact_table = _load_fact_table(
        s3,
        bucket,
        prefix,
    )

    _validate_fact_schema(fact_table)
    _validate_fact_data(fact_table)


def _validate_partitions(
    s3,
    bucket: str,
    prefix: str,
) -> None:
    partition_dirs: set[str] = set()

    paginator = s3.get_paginator(
        "list_objects_v2"
    )

    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=f"{prefix}/fact_orders/",
    ):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if (
                "order_year=" in key
                and "order_month=" in key
            ):
                partition_dirs.add(
                    key.rsplit("/", 1)[0] + "/"
                )

    if partition_dirs:
        print(
            f"OK: Hive partitions detected "
            f"({len(partition_dirs)} path(s))"
        )
    else:
        print(
            "WARN: no order_year=/order_month= "
            "paths found yet"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate S3 analytics outputs."
    )
    parser.add_argument(
        "--region",
        default=None,
    )

    args = parser.parse_args()

    try:
        bucket, prefix = _get_config()

        s3 = boto3.client(
            "s3",
            region_name=args.region,
        )

        print(
            f"Validating s3://{bucket}/{prefix}/"
        )

        _validate_dimension_tables(
            s3,
            bucket,
            prefix,
        )

        _validate_fact_orders(
            s3,
            bucket,
            prefix,
        )

        _validate_partitions(
            s3,
            bucket,
            prefix,
        )

        print("Validation passed.")
        return 0

    except subprocess.CalledProcessError as exc:
        print(
            f"Terraform output failed: {exc}",
            file=sys.stderr,
        )
        return 1

    except Exception as exc:
        print(
            f"Validation failed: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())