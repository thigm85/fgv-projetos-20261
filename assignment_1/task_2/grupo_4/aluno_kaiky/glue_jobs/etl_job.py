"""
AWS Glue ETL Job: classicmodels OLTP -> star schema -> S3 Parquet.
"""

from __future__ import annotations

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F

from constants import (
    FACT_TABLE_NAME,
    SALES_AMOUNT_MAX_DELTA_GLUE,
    STAR_REFERENTIAL_KEYS,
    STAR_SCHEMA_OUTPUT_TABLES,
)
from transformations.dim_countries import build_dim_countries
from transformations.dim_customers import build_dim_customers
from transformations.dim_dates import build_dim_dates
from transformations.dim_products import build_dim_products
from transformations.fact_orders import build_fact_orders

from utils.extract import extract_all
from utils.helpers import get_job_logger, parse_job_args, require_non_empty
from utils.load import load_all_star_schema


class ETLJob:
    """
    Encapsulates the full ETL pipeline:
    extract -> transform -> validate -> load
    """

    def __init__(self):
        self.logger = get_job_logger()
        self.args = parse_job_args(sys.argv)

        self.connection_name = self.args["GLUE_CONNECTION_NAME"]
        self.s3_out = self.args["S3_OUTPUT_PATH"].rstrip("/")
        self.database = self.args["RDS_DATABASE"]

        # Spark / Glue setup
        sc = SparkContext()
        self.glue_context = GlueContext(sc)
        self.spark = self.glue_context.spark_session

        self.job = Job(self.glue_context)
        self.job.init(self.args["JOB_NAME"], self.args)

        # Data holders
        self.raw = None
        self.star_tables = None

    # =========================
    # EXTRACT
    # =========================
    def extract(self):
        """Extract raw data from source."""
        self.logger.info("Extracting data")

        self.raw = extract_all(
            self.glue_context,
            self.connection_name,
            self.database,
            self.logger,
        )

        for table_name, df in self.raw.items():
            require_non_empty(df, f"raw.{table_name}", self.logger)

    # =========================
    # TRANSFORM
    # =========================
    def transform(self):
        """Build star schema."""
        self.logger.info("Transforming data")

        dim_customers = build_dim_customers(self.raw["customers"], self.logger)
        dim_products = build_dim_products(self.raw["products"], self.logger)
        dim_countries = build_dim_countries(
            self.raw["customers"], self.raw["offices"], self.logger
        )
        dim_dates = build_dim_dates(self.raw["orders"], self.logger)

        fact = build_fact_orders(
            self.raw["orderdetails"],
            self.raw["orders"],
            self.raw["customers"],
            dim_countries,
            self.logger,
        )

        self.star_tables = dict(
            zip(
                STAR_SCHEMA_OUTPUT_TABLES,
                (
                    fact,
                    dim_customers,
                    dim_products,
                    dim_dates,
                    dim_countries,
                ),
            )
        )

    # =========================
    # VALIDATIONS
    # =========================
    def _count_orphans(self, fact_df, dim_df, condition):
        return fact_df.join(dim_df, condition, "left_anti").count()

    def _validate_referential_integrity(self):
        """Ensure no orphan records exist."""
        fact = self.star_tables[FACT_TABLE_NAME]

        for dim_name, fact_col, dim_col in STAR_REFERENTIAL_KEYS:
            dim_df = self.star_tables[dim_name]
            cond = fact[fact_col] == dim_df[dim_col]
            orphan_count = self._count_orphans(fact, dim_df, cond)

            if orphan_count > 0:
                raise ValueError(
                    f"{FACT_TABLE_NAME} has {orphan_count} orphan rows vs {dim_name}"
                )

    def _validate_sales_amount(self):
        """Validate business rule: sales_amount ≈ quantity * price."""
        fact = self.star_tables[FACT_TABLE_NAME]

        expected = F.col("quantity_ordered").cast("decimal(24,8)") * F.col("price_each").cast("decimal(24,8)")
        delta = F.abs(F.col("sales_amount").cast("decimal(24,8)") - expected)

        mismatch_df = fact.where(delta > F.lit(SALES_AMOUNT_MAX_DELTA_GLUE))
        mismatch_count = mismatch_df.count()

        if mismatch_count > 0:
            sample = mismatch_df.select(
                "quantity_ordered", "price_each", "sales_amount"
            ).take(5)

            raise ValueError(
                f"sales_amount inconsistent with qty*price rows={mismatch_count} sample={sample}"
            )

    def validate(self):
        """Run all validations."""
        self.logger.info("Validating data")

        fact = self.star_tables[FACT_TABLE_NAME]
        require_non_empty(fact, FACT_TABLE_NAME, self.logger)

        self._validate_referential_integrity()
        self._validate_sales_amount()

        self.logger.info("All validations passed")

    # =========================
    # LOAD
    # =========================
    def load(self):
        """Load data to S3."""
        self.logger.info("Loading data")

        load_all_star_schema(self.star_tables, self.s3_out, self.logger)

    # =========================
    # RUN
    # =========================
    def run(self):
        """Execute full pipeline."""
        self.logger.info(
            "Starting ETL: database=%s output=%s",
            self.database,
            self.s3_out,
        )

        self.extract()
        self.transform()
        self.validate()
        self.load()

        self.logger.info("ETL completed successfully")
        self.job.commit()


# =========================
# ENTRYPOINT
# =========================

def main():
    job = ETLJob()
    job.run()


if __name__ == "__main__":
    main()