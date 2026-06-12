# Assignment 2 - Task 2

Incremental Glue ETL for `classicmodels`.

This task reads the `etl_watermark` created in Task 1, extracts only new orders from RDS through JDBC, writes the analytics star schema to S3, partitions `fact_orders` by `order_year` and `order_month`, and schedules the pipeline with EventBridge.

## Structure

- `glue/incremental_etl.py`: PySpark Glue job with watermark filtering and partition merge logic.
- `terraform/`: RDS, S3, Glue Catalog, Glue Job, Glue Workflow, and EventBridge schedule.
- `evidence/run_log.md`: execution evidence template.
- `.env.example`: local environment template for AWS and Terraform variables.

## Setup

```bash
cd assignment_2/task_2
cp .env.example .env
```

Fill the AWS credentials and database password values in `.env`, then export them in your shell before running Terraform:

```bash
set -a
source .env
set +a
```

## Deploy

```bash
cd assignment_2/task_2/terraform
terraform init
terraform plan
terraform apply
```

The Terraform module uploads `../glue/incremental_etl.py` to S3 and configures the Glue job to use it.

## Glue Job Contract

The job expects the Task 1 watermark table:

```sql
etl_watermark(
  pipeline_name,
  last_processed_order_date,
  last_run_at,
  last_run_status
)
```

For `pipeline_name = 'classicmodels_sales'`, the job reads `last_processed_order_date` and extracts:

```sql
SELECT * FROM orders WHERE orderDate > <watermark>
```

On success, it advances `last_processed_order_date` to `MAX(orderDate)` from the processed delta and marks `last_run_status = 'SUCCEEDED'`. On failure, it marks `last_run_status = 'FAILED'` without advancing the date.

## Output Layout

`fact_orders` is written in Hive-style partitions:

```text
s3://<bucket>/analytics/fact_orders/order_year=YYYY/order_month=MM/
```

The Glue Catalog table declares `order_year` and `order_month` as partition keys so Athena can prune partitions.

## Schedule

EventBridge rule:

```text
cron(0 12 ? * MON *)
```

It triggers the Glue workflow `<resource_name_prefix>-workflow`, which starts the Glue job from `var.glue_job_name`.

The lab setup uses the AWS Academy `LabRole` discovered with:

```hcl
data "aws_iam_role" "lab_role" {
  name = "LabRole"
}
```

If the lab blocks EventBridge or Glue permissions on `LabRole`, document the error and run the Glue job manually for evidence.
