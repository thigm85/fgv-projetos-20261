#!/usr/bin/env python3
"""
Post-ETL validation: verify Parquet outputs in S3 and basic business rules.
"""

from __future__ import annotations

import argparse
import io
import sys
from decimal import Decimal
from pathlib import Path

import boto3
import pyarrow.parquet as pq

_GLUE_JOBS = Path(__file__).resolve().parents[1] / "glue_jobs"
if str(_GLUE_JOBS) not in sys.path:
    sys.path.insert(0, str(_GLUE_JOBS))

import constants as C 


class ETLValidator:
    """
    Validate ETL outputs stored as Parquet files in S3.
    """

    def __init__(self, bucket: str, prefix: str, region: str | None = None):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.s3 = boto3.client("s3", region_name=region)

    # =========================
    # S3 HELPERS
    # =========================

    def _first_parquet_key(self, table: str) -> str | None:
        """Return first Parquet file key for a given table."""
        prefix = f"{self.prefix}/{table}/"

        paginator = self.s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".parquet"):
                    return key

        return None

    def _read_parquet(self, key: str):
        """Read Parquet file from S3 into Arrow table."""
        body = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return pq.read_table(io.BytesIO(body), use_threads=True)

    # =========================
    # VALIDATIONS
    # =========================

    def validate_tables_exist(self):
        """Ensure all expected tables exist in S3."""
        print("Checking table existence...")

        for table in C.STAR_SCHEMA_OUTPUT_TABLES:
            key = self._first_parquet_key(table)

            if not key:
                raise ValueError(
                    f"No Parquet found under s3://{self.bucket}/{self.prefix}/{table}/"
                )

            print(f"OK: {table} -> s3://{self.bucket}/{key}")

    def validate_fact_schema(self, table):
        """Ensure fact_orders contains required columns."""
        names = set(table.column_names)
        missing = C.FACT_COLUMNS - names

        if missing:
            raise ValueError(f"{C.FACT_TABLE_NAME} missing columns: {missing}")

    def validate_sales_amount(self, table, sample_size: int = 10_000):
        """
        Validate business rule:
        sales_amount ≈ quantity_ordered * price_each
        """
        qty = table.column("quantity_ordered").to_pylist()
        price = table.column("price_each").to_pylist()
        sales = table.column("sales_amount").to_pylist()

        n = min(table.num_rows, sample_size)

        for i in range(n):
            q = int(qty[i]) if qty[i] is not None else None
            pr = Decimal(str(price[i])) if price[i] is not None else None
            sa = Decimal(str(sales[i])) if sales[i] is not None else None

            if q is None or pr is None or sa is None:
                raise ValueError(f"Null metric at row {i}")

            expected = (Decimal(q) * pr).quantize(Decimal("0.0001"))

            if abs(sa - expected) > C.SALES_AMOUNT_MAX_DELTA_VALIDATE:
                raise ValueError(
                    f"sales_amount mismatch at row {i}: got {sa}, expected ~{expected}"
                )

    def validate_fact_table(self):
        """Run all validations specific to fact_orders."""
        print(f"Validating {C.FACT_TABLE_NAME}...")

        key = self._first_parquet_key(C.FACT_TABLE_NAME)
        assert key is not None

        table = self._read_parquet(key)

        self.validate_fact_schema(table)
        self.validate_sales_amount(table)

        print(f"OK: {C.FACT_TABLE_NAME} schema and business rules validated")

    # =========================
    # RUN
    # =========================

    def run(self):
        """Execute all validations."""
        self.validate_tables_exist()
        self.validate_fact_table()

        print("All validations passed")


# =========================
# CLI
# =========================


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate Glue ETL Parquet outputs on S3."
    )

    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--region", default=None)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        validator = ETLValidator(
            bucket=args.bucket,
            prefix=args.prefix,
            region=args.region,
        )
        validator.run()
        return 0

    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
