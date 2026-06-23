"""Dimension: products."""

from __future__ import annotations

import logging

from pyspark.sql import DataFrame


def build_dim_products(products: DataFrame, logger: logging.Logger) -> DataFrame:
    logger.info("Building dim_products")
    return products.select(
        products["productCode"].alias("product_id"),
        products["productName"].alias("product_name"),
        products["productLine"].alias("product_line"),
        products["productVendor"].alias("product_vendor"),
    ).dropDuplicates(["product_id"])
