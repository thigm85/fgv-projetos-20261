# Assignment 2 — Task 2: Incremental ETL (classicmodels → Parquet DW)

## What this does

A weekly-triggered AWS Glue job reads only the orders newer than the last
watermark from the classicmodels RDS database, builds a star-schema data
warehouse as Parquet files on S3, and registers the new partitions in the
Glue Data Catalog so they are immediately queryable via Athena.

### Output tables

| Table | Type | Partitioned? |
|---|---|---|
| `dim_customers` | Dimension | No |
| `dim_products` | Dimension | No |
| `dim_dates` | Dimension (full history) | No |
| `dim_countries` | Dimension | No |
| `fact_orders` | Fact | Yes: `order_year` / `order_month` |

## Design decisions

| Decision | Choice | Reason |
|---|---|---|
| Watermark read | Strict NULL check → error | Fails fast instead of silently reprocessing all history |
| `dim_dates` source | All orders (not just delta) | Guarantees a complete, non-sparse date dimension |
| `dim_countries` territory | Geographic mapping function | No NULLs from missing salesRep data; deterministic |
| `country_key` | `dense_rank()` integer | Better Athena join performance than string/hash keys |
| Fact merge | Per-partition upsert with `localCheckpoint` | Idempotent; prevents re-computing large RDDs after union |
| S3 delete before dim overwrite | Version-aware `list_object_versions` | Required for versioned S3 buckets; avoids ghost versions |
| Athena partition discovery | Partition projection | No `MSCK REPAIR TABLE` needed; works immediately after write |
| Glue Catalog registration | `BatchCreatePartition` API | Partitions available to all catalog-based tools instantly |
| Quality gate | Count > 0 + `sales_amount` integrity | Fails before writing if data is corrupt |

## Directory structure

```
assignment_2/task_2/antonio_brych/
├── scripts/
│   ├── glue_incremental_etl.py     # Glue job (upload to S3 via Terraform)
│   ├── init_watermark.py           # Run once before first ETL
│   ├── simulate_new_orders.py      # Insert test orders to validate incremental logic
│   └── validate_incremental_etl.py # Post-run Athena validation checks
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── evidence/
│   └── run_log.md
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup & execution

### 1. Local prerequisites

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your RDS credentials
```

### 2. Initialise watermark (run once)

```bash
python scripts/init_watermark.py
```

### 3. Deploy infrastructure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in required values
terraform init
terraform apply
```

### 4. Run the Glue job manually (first time)

```bash
aws glue start-job-run --job-name classicmodels-incremental-etl
```

After the first run the EventBridge Scheduler fires every Monday at 12:00 UTC.

### 5. Simulate new orders and re-run

```bash
python scripts/simulate_new_orders.py --count 10
aws glue start-job-run --job-name classicmodels-incremental-etl
```

### 6. Validate results

```bash
python scripts/validate_incremental_etl.py
```

## Incremental logic

```
last_watermark = etl_watermark.last_processed_order_date

SELECT * FROM orders WHERE orderDate > last_watermark  → orders_delta
SELECT * FROM orderdetails WHERE order IN orders_delta  → orderdetails_delta

build star-schema from delta
quality gates (row count > 0, sales_amount integrity)
overwrite dimension tables
upsert fact partitions touched by this delta
register new (order_year, order_month) partitions in Glue Catalog
UPDATE etl_watermark SET last_processed_order_date = MAX(orders_delta.orderDate)
```
