resource "aws_glue_catalog_database" "star_schema" {
  name = "${var.project_name}-db"
}

resource "aws_glue_catalog_table" "fact_orders" {
  name = "fact_orders"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.data_lake.id}/output/fact_orders/"
    input_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
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
}

resource "aws_glue_catalog_table" "dim_customers" {
  name = "dim_customers"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.data_lake.id}/output/dim_customers/"
    input_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
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

resource "aws_glue_catalog_table" "dim_products" {
  name          = "dim_products"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.data_lake.id}/output/dim_products/"
    input_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
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

resource "aws_glue_catalog_table" "dim_dates" {
  name          = "dim_dates"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.id}/output/dim_dates/"
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

resource "aws_glue_catalog_table" "dim_countries" {
  name = "dim_countries"
  database_name = aws_glue_catalog_database.star_schema.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.data_lake.id}/output/dim_countries/"
    input_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
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

resource "aws_athena_workgroup" "main" {
  name = "${var.project_name}-workgroup"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_lake.id}/athena-results/"
    }
  }

  force_destroy = true
}
