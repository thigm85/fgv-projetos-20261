# Tabela particionada no Glue Catalog/Athena.
# O job também recria/recupera partições com MSCK REPAIR TABLE.
# Este recurso deixa o contrato visível no Terraform.

resource "aws_glue_catalog_table" "fact_orders" {
  name          = "fact_orders"
  database_name = var.glue_database_name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL              = "TRUE"
    "classification"     = "parquet"
    "parquet.compression" = "SNAPPY"
  }

  partition_keys {
    name = "order_year"
    type = "int"
  }

  partition_keys {
    name = "order_month"
    type = "int"
  }

  storage_descriptor {
    location      = "s3://${var.analytics_bucket}/analytics/fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "fact_orders_parquet_serde"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "order_id"
      type = "int"
    }
    columns {
      name = "product_id"
      type = "string"
    }
    columns {
      name = "customer_id"
      type = "int"
    }
    columns {
      name = "order_date"
      type = "date"
    }
    columns {
      name = "required_date"
      type = "date"
    }
    columns {
      name = "shipped_date"
      type = "date"
    }
    columns {
      name = "status"
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
    columns {
      name = "order_line_number"
      type = "int"
    }
  }
}
