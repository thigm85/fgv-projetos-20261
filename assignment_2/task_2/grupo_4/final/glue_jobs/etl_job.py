"""
AWS Glue entrypoint: incremental classicmodels star-schema ETL.
"""

from __future__ import annotations
import sys
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from constants import DIM_MERGE_CONFIG, PIPELINE_NAME_DEFAULT, WATERMARK_TABLE_DEFAULT, watermark_date_str
from pipeline.extract import extract_delta, read_watermark
from pipeline.load import merge_fact_partitions, merge_into_prefix, register_fact_partitions, update_watermark
from pipeline.transform import build_dimensions, build_fact_orders
from pipeline.validate import validate_delta
from pyspark.context import SparkContext
from pyspark.sql import functions as F

JOB_ARG_NAMES = [
    "JOB_NAME",
    "rds_endpoint",
    "rds_port",
    "db_name",
    "db_user",
    "db_password",
    "s3_bucket",
    "out_prefix",
    "glue_database",
    "pipeline_name",
    "watermark_table",
]

class IncrementalETLJob:
    """Watermark-driven incremental pipeline."""

    def __init__(self, args: dict):
        self.args = args

        sc = SparkContext.getOrCreate()
        self.glue_context = GlueContext(sc)
        self.spark = self.glue_context.spark_session

        self.jdbc_url = (
            f"jdbc:mysql://{args['rds_endpoint']}:"
            f"{args['rds_port']}/{args['db_name']}"
        )

        self.db_user = args["db_user"]
        self.db_password = args["db_password"]

        self.pipeline_name = args.get(
            "pipeline_name",
            PIPELINE_NAME_DEFAULT,
        )

        self.watermark_table = args.get(
            "watermark_table",
            WATERMARK_TABLE_DEFAULT,
        )

        self.glue_database = args["glue_database"]

        out_prefix = args["out_prefix"].strip("/")

        self.base_path = (
            f"s3://{args['s3_bucket']}/{out_prefix}"
        )

        self.fact_base_path = (
            f"{self.base_path}/fact_orders"
        )

    def _read_watermark(self) -> dict:
        return read_watermark(
            spark=self.spark,
            jdbc_url=self.jdbc_url,
            user=self.db_user,
            password=self.db_password,
            pipeline_name=self.pipeline_name,
            watermark_table=self.watermark_table,
        )

    def _update_watermark(
        self,
        *,
        status: str,
        last_processed_order_date,
    ) -> None:
        update_watermark(
            spark=self.spark,
            jdbc_url=self.jdbc_url,
            user=self.db_user,
            password=self.db_password,
            pipeline_name=self.pipeline_name,
            watermark_table=self.watermark_table,
            status=status,
            last_processed_order_date=last_processed_order_date,
        )

    def _extract_delta(self, cutoff: str):
        return extract_delta(
            spark=self.spark,
            jdbc_url=self.jdbc_url,
            user=self.db_user,
            password=self.db_password,
            cutoff=cutoff,
        )

    def _handle_empty_delta(
        self,
        watermark: dict,
    ) -> None:
        print(
            "No new orders since watermark; "
            "finishing without lake changes."
        )

        self._update_watermark(
            status="SUCCEEDED",
            last_processed_order_date=watermark[
                "last_processed_order_date"
            ],
        )

    def _merge_dimensions(
        self,
        dims: dict,
    ) -> None:
        for dim_name, (keys, cols) in DIM_MERGE_CONFIG.items():
            dim_path = (
                f"{self.base_path}/{dim_name}/"
            )

            if merge_into_prefix(
                spark=self.spark,
                delta_df=dims[dim_name],
                base_path=dim_path,
                merge_keys=keys,
                data_columns=cols,
            ):
                print(
                    f"Merged {dim_name} "
                    f"at {dim_path}"
                )

    def _merge_fact(
        self,
        delta_fact,
    ) -> list[tuple[int, int]]:
        touched = merge_fact_partitions(
            spark=self.spark,
            delta_fact=delta_fact,
            fact_base_path=self.fact_base_path,
        )

        print(
            f"fact_orders partitions "
            f"updated: {touched}"
        )

        return touched

    def _register_partitions(
        self,
        partitions: list[tuple[int, int]],
    ) -> None:
        try:
            register_fact_partitions(
                glue_database=self.glue_database,
                fact_base_path=self.fact_base_path,
                partitions=partitions,
            )

        except Exception as exc:
            print(
                "Partition registration note "
                f"(may already exist): {exc}"
            )

    def _max_order_date(self, orders_df):
        return (
            orders_df
            .agg(
                F.max(
                    F.to_date("orderDate")
                ).alias("max_dt")
            )
            .collect()[0]["max_dt"]
        )

    def _process_delta(self, delta):
        dims = build_dimensions(
            orders_delta=delta.orders,
            orderdetails_delta=delta.orderdetails,
            customers=delta.customers,
            products=delta.products,
            productlines=delta.productlines,
            employees=delta.employees,
            offices=delta.offices,
        )

        delta_fact = build_fact_orders(
            orderdetails_delta=delta.orderdetails,
            orders_delta=delta.orders,
            customers=delta.customers,
        )

        validate_delta(
            spark=self.spark,
            delta_fact=delta_fact,
            dims=dims,
        )

        self._merge_dimensions(dims)

        touched = self._merge_fact(
            delta_fact,
        )

        self._register_partitions(
            touched,
        )

        return self._max_order_date(
            delta.orders,
        )

    def run(self) -> None:
        watermark = self._read_watermark()

        cutoff = watermark_date_str(
            watermark[
                "last_processed_order_date"
            ]
        )

        print(
            "Incremental cutoff: "
            f"orderDate > {cutoff} "
            f"(status={watermark['last_run_status']})"
        )

        try:
            delta = self._extract_delta(
                cutoff,
            )

            if delta is None:
                self._handle_empty_delta(
                    watermark,
                )
                return

            max_order_date = (
                self._process_delta(
                    delta,
                )
            )

            self._update_watermark(
                status="SUCCEEDED",
                last_processed_order_date=max_order_date,
            )

            print(
                "Watermark advanced to "
                f"{max_order_date}"
            )

        except Exception as exc:
            print(
                f"ETL failed: {exc}"
            )

            self._update_watermark(
                status="FAILED",
                last_processed_order_date=None,
            )

            raise


def main() -> None:
    IncrementalETLJob(getResolvedOptions(sys.argv, JOB_ARG_NAMES)).run()


if __name__ == "__main__":
    main()
