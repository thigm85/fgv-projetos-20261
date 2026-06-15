# Assignment 2 — Task 1: Incremental source and watermark

**Group 4**

Prepares thae `clssicmodels` OLTP database (MySQL on RDS) for incremental ETL:

- Control metadata in `etl_watermark`
- Scripts to simulate new orders
- Validation with deterministic exit codes

## Prerequisites

- RDS MySQL instance with database `classicmodels` already loaded (assignment_1 / task_1)
- Python 3.10+
- AWS credentials with `rds:DescribeDBInstances` (to resolve `DB_HOST` automatically)
- Network access to the RDS endpoint (security group / VPN)

## Setup

```bash
cd assignment_2/task_1/grupo_4/aluno_kaiky
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
```

Edit `.env` with your credentials (do **not** commit `.env`). Leave `DB_HOST` empty — the first script run resolves it via AWS and saves it to `.env`:

| Variable | Description |
|----------|-------------|
| `DB_HOST` | RDS hostname (empty = resolved automatically in `load_settings()`) |
| `DB_PORT` | MySQL port (default `3306`) |
| `DB_NAME` | Database name (`classicmodels`) |
| `DB_USER` | MySQL user |
| `DB_PASSWORD` | MySQL password |
| `RDS_DB_INSTANCE_IDENTIFIER` | RDS instance id in AWS (default `classicmodels-mysql-g4`) |
| `AWS_REGION` | Region where RDS lives (default `us-east-1`) |
| `SIMULATE_ORDER_COUNT` | Default for `--count` (optional, default `5`) |

## Suggested flow

```text
1. init_watermark              → create/seed etl_watermark from MAX(orders.orderDate)
2. validate_incremental_source → baseline checks (no pending data required)
3. simulate_new_orders         → insert new orders beyond the watermark
4. validate_incremental_source --require-pending → confirm pending incremental data
```

### Commands

```bash
# 1 — Initialize watermark (idempotent; resolves DB_HOST first if .env has it empty)
python scripts/init_watermark.py

# 2 — Validate baseline
python scripts/validate_incremental_source.py

# 3 — Simulate new orders (does NOT update etl_watermark)
python scripts/simulate_new_orders.py --count 5
python scripts/simulate_new_orders.py --count 10 --seed 42

# 4 — Validate after simulation
python scripts/validate_incremental_source.py --require-pending

# Optional: run all four steps
python main.py --count 5 --seed 42

# Optional: drop etl_watermark only (does not delete simulated orders)
python scripts/drop_watermark.py
```

## `etl_watermark` contract

| Column | Type | Description |
|--------|------|-------------|
| `pipeline_name` | `VARCHAR(64)` PK | Fixed value: `classicmodels_sales` |
| `last_processed_order_date` | `DATE` | Greatest `orders.orderDate` already in the analytical lake |
| `last_run_at` | `DATETIME` | UTC timestamp of last successful ETL (updated in Task 2) |
| `last_run_status` | `VARCHAR(32)` | e.g. `NEVER_RUN`, `SUCCEEDED`, `FAILED` |

## Project layout

```text
aluno_kaiky/
├── .env.example
├── README.md
├── requirements.txt
├── main.py                         # optional: runs the 4 README steps in order
├── scripts/                        # thin CLIs: argparse + exit code
│   ├── _bootstrap.py               # shared sys.path setup for scripts
│   ├── init_watermark.py
│   ├── drop_watermark.py           # optional teardown of etl_watermark
│   ├── simulate_new_orders.py
│   └── validate_incremental_source.py
├── src/
│   └── models.py                   # Watermark, SimulationSummary, …
└── utils/
    ├── config.py                   # .env → Settings
    ├── rds_discovery.py            # fills DB_HOST via AWS when empty
    ├── database.py                 # MySQL connection
    ├── cli.py                      # shared print/format helpers
    ├── tasks.py                    # one runnable op per script (init / simulate / validate)
    ├── watermark.py
    ├── order_simulator.py
    └── validator.py
```

**Layering:** `scripts/*.py` parse CLI flags → `utils/tasks.py` runs the work → domain modules (`watermark`, `order_simulator`, `validator`) hold the logic. `main.py` only chains the three tasks + validation twice (README flow).

## Business rules

- Watermark is based on `orders.orderDate`.
- Simulated `orderdetails` use `sales_amount = quantityOrdered * priceEach` (star-schema rule for Task 2).
- `simulate_new_orders.py` never updates `etl_watermark` (Task 2 Glue job responsibility).
- Each simulated order is inserted in a transaction (`orders` + `orderdetails`).

## Validation exit codes

| Code | Meaning |
|------|---------|
| `0` | All checks passed |
| `1` | One or more checks failed or connection error |

Checks:

1. Table `etl_watermark` exists with row `classicmodels_sales`
2. `last_processed_order_date` is not `NULL`
3. Pending data: with `--require-pending`, `MAX(orders.orderDate) > last_processed_order_date`
4. Orders beyond the watermark have at least one `orderdetails` row

## What this task does not do

- Does not modify the star schema on S3 (Task 2)
- Does not run or schedule Glue jobs (Task 2)
- Does not commit credentials or full database dumps
