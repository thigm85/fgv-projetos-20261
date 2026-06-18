# ---------------------------------------------------------------------------
# Glue Catalog Database
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "star_schema" {
  name = "${var.project_name}-db"
}

# ---------------------------------------------------------------------------
# fact_orders — partitioned by order_year / order_month
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "fact_orders" {
  name          = "fact_orders"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.id}/analytics/fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "order_id"
      type = "int"
    }
    columns {
      name = "customer_id"
      type = "int"
    }
    columns {
      name = "product_id"
      type = "string"
    }
    columns {
      name = "order_date_key"
      type = "int"
    }
    columns {
      name = "country_key"
      type = "string"
    }
    columns {
      name = "quantity_ordered"
      type = "int"
    }
    columns {
      name = "price_each"
      type = "double"
    }
    columns {
      name = "sales_amount"
      type = "double"
    }
  }

  # Partition keys for Hive-style partitioning
  partition_keys {
    name = "order_year"
    type = "int"
  }
  partition_keys {
    name = "order_month"
    type = "int"
  }
}

# ---------------------------------------------------------------------------
# dim_customers
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_customers" {
  name          = "dim_customers"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.id}/analytics/dim_customers/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "customer_id"
      type = "int"
    }
    columns {
      name = "customer_name"
      type = "string"
    }
    columns {
      name = "contact_name"
      type = "string"
    }
    columns {
      name = "city"
      type = "string"
    }
    columns {
      name = "country"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# dim_products
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_products" {
  name          = "dim_products"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.id}/analytics/dim_products/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "product_id"
      type = "string"
    }
    columns {
      name = "product_name"
      type = "string"
    }
    columns {
      name = "product_line"
      type = "string"
    }
    columns {
      name = "product_vendor"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# dim_dates
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_dates" {
  name          = "dim_dates"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.id}/analytics/dim_dates/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "date_key"
      type = "int"
    }
    columns {
      name = "full_date"
      type = "date"
    }
    columns {
      name = "year"
      type = "int"
    }
    columns {
      name = "quarter"
      type = "int"
    }
    columns {
      name = "month"
      type = "int"
    }
    columns {
      name = "day"
      type = "int"
    }
  }
}

# ---------------------------------------------------------------------------
# dim_countries
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_countries" {
  name          = "dim_countries"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.id}/analytics/dim_countries/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "country_key"
      type = "string"
    }
    columns {
      name = "country"
      type = "string"
    }
    columns {
      name = "territory"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# Athena Workgroup
# ---------------------------------------------------------------------------

resource "aws_athena_workgroup" "main" {
  name = "${var.project_name}-workgroup"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_lake.id}/athena-results/"
    }
  }

  force_destroy = true
}
