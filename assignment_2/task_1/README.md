# Assignment 2 - Task 1

Incremental source setup for the `classicmodels` MySQL database.

It creates a watermark table, simulates new OLTP orders, and validates that the database is ready for the next incremental ETL.

## Structure

- `scripts/common.py`: database connection and environment loading.
- `scripts/init_watermark.py`: creates and initializes `etl_watermark`.
- `scripts/simulate_new_orders.py`: inserts new rows in `orders` and `orderdetails`.
- `scripts/validate_incremental_source.py`: validates watermark state and pending rows.
- `run_task1.sh`: runs the incremental-source flow against an existing database.
- `provision_new_rds.sh`: creates a new RDS instance, loads `classicmodels`, and runs the flow.
- `.env.example`: environment template.

## Setup

```bash
cd assignment_2/task_1
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For an existing database, fill:

```bash
DB_HOST=<rds-endpoint>
DB_PORT=3306
DB_NAME=classicmodels
DB_USER=<user>
DB_PASSWORD=<password>
```

For a new RDS instance, fill the AWS credential fields and keep the RDS values from the template or adjust the names.

## Existing Database Flow

Run each step manually:

```bash
python scripts/init_watermark.py
python scripts/validate_incremental_source.py
python scripts/simulate_new_orders.py --count 5 --seed 42
python scripts/validate_incremental_source.py --require-pending
```

Or run the same flow with one command:

```bash
COUNT=5 SEED=42 ./run_task1.sh
```

## New RDS Flow

```bash
COUNT=5 SEED=42 ./provision_new_rds.sh
```

This creates the database instance, loads the sample `classicmodels` data, initializes the watermark, simulates new orders, and validates pending rows.

## Watermark Contract

The script creates:

```sql
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name VARCHAR(64) PRIMARY KEY,
    last_processed_order_date DATE,
    last_run_at DATETIME NULL,
    last_run_status VARCHAR(32) NOT NULL
);
```

The row uses:

```text
pipeline_name = classicmodels_sales
```

`last_processed_order_date` starts at `MAX(orders.orderDate)`. The simulator does not update the watermark because the future ETL should only update it after a successful incremental load.

## Useful Options

Dry-run the simulation without committing changes:

```bash
python scripts/simulate_new_orders.py --count 5 --seed 42 --dry-run
```

Choose a first simulated order date:

```bash
python scripts/simulate_new_orders.py --count 3 --start-date 2026-06-10
```

Allow weekend dates:

```bash
python scripts/simulate_new_orders.py --count 3 --allow-weekends
```
