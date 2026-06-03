"""
2_validate_athena.py — Valida as consultas Athena obrigatórias da Task 3.

Critérios de aceitação
----------------------
- 4.2  dim_products retorna ≥ 1 linha com as colunas: product_id,
       product_name, product_line, product_vendor.
- 4.3  Totais por país retornam ≥ 1 linha com country e total_sales > 0.
- 4.4  Detalhamento retorna ≥ 1 linha com full_date, product_line,
       product_name, country e total_sales.
- Consistência: nenhum registro em fact_orders onde
  ABS(sales_amount − quantity_ordered × price_each) > 0.01.

Pré-requisitos
--------------
- 1_setup_catalog.py já executado com sucesso (catalog_info.json presente).
- Variáveis AWS no .env.

Uso
---
    cd assignment_1/task_3/grupo_3/henrique_borges
    python 2_validate_athena.py

Exit codes
----------
- 0  Todas as consultas e verificações passaram.
- 1  Variável ausente, catalog_info.json ausente ou ≥ 1 verificação falhou.
"""

import json
import os
import sys
from pathlib import Path

import boto3
import awswrangler as wr
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

REQUIRED_VARS = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]


def check_env() -> None:
    """Verifica que as credenciais AWS obrigatórias estão no .env.

    Encerra o processo com exit code 1 listando todas as variáveis ausentes.
    """
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print(f"[ERRO] Variáveis ausentes no .env: {', '.join(missing)}")
        sys.exit(1)


check_env()

CATALOG_INFO = HERE / "catalog_info.json"
if not CATALOG_INFO.exists():
    print("[ERRO] catalog_info.json não encontrado. Execute 1_setup_catalog.py primeiro.")
    sys.exit(1)

info = json.loads(CATALOG_INFO.read_text())
GLUE_DATABASE = info["glue_database"]
ATHENA_OUTPUT = info["athena_output"]

boto_session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)

QUERIES = {
    "4.2 — dim_products (exploratória)": {
        "sql": """
            SELECT product_id, product_name, product_line, product_vendor
            FROM dim_products
            LIMIT 20
        """,
        "min_rows": 1,
        "check_cols": ["product_id", "product_name", "product_line", "product_vendor"],
    },
    "4.3 — Vendas totais por país": {
        "sql": """
            SELECT dim_countries.country,
                   SUM(fact_orders.sales_amount) AS total_sales
            FROM fact_orders
            JOIN dim_countries ON fact_orders.country_key = dim_countries.country_key
            GROUP BY dim_countries.country
            ORDER BY total_sales DESC
            LIMIT 10
        """,
        "min_rows": 1,
        "check_cols": ["country", "total_sales"],
        "check": lambda df: (df["total_sales"] > 0).all(),
        "check_msg": "total_sales deve ser > 0",
    },
    "4.4 — Detalhamento por data, linha, produto e país": {
        "sql": """
            SELECT dim_dates.full_date,
                   dim_products.product_line,
                   dim_products.product_name,
                   dim_countries.country,
                   SUM(fact_orders.sales_amount) AS total_sales
            FROM fact_orders
            JOIN dim_products  ON fact_orders.product_id      = dim_products.product_id
            JOIN dim_countries ON fact_orders.country_key     = dim_countries.country_key
            JOIN dim_dates     ON fact_orders.order_date_key  = dim_dates.date_key
            GROUP BY dim_dates.full_date,
                     dim_products.product_line,
                     dim_products.product_name,
                     dim_countries.country
            LIMIT 10
        """,
        "min_rows": 1,
        "check_cols": ["full_date", "product_line", "product_name", "country", "total_sales"],
    },
    "Consistência — sales_amount == quantity_ordered * price_each": {
        "sql": """
            SELECT COUNT(*) AS inconsistencias
            FROM fact_orders
            WHERE ABS(sales_amount - (quantity_ordered * price_each)) > 0.01
        """,
        "min_rows": 1,
        "check_cols": ["inconsistencias"],
        "check": lambda df: int(df["inconsistencias"].iloc[0]) == 0,
        "check_msg": "sales_amount diverge de quantity_ordered * price_each em alguns registros",
    },
}

errors = []

for name, spec in QUERIES.items():
    print(f"\n[Testando] {name}")
    try:
        df = wr.athena.read_sql_query(
            sql=spec["sql"],
            database=GLUE_DATABASE,
            s3_output=ATHENA_OUTPUT,
            boto3_session=boto_session,
        )

        # Valida número mínimo de linhas
        if len(df) < spec["min_rows"]:
            raise AssertionError(f"Esperado >= {spec['min_rows']} linha(s), obtido {len(df)}")

        # Valida colunas esperadas
        missing_cols = [c for c in spec.get("check_cols", []) if c not in df.columns]
        if missing_cols:
            raise AssertionError(f"Colunas ausentes: {missing_cols}")

        # Validação customizada (opcional)
        if "check" in spec and not spec["check"](df):
            raise AssertionError(spec["check_msg"])

        print(f"  [OK] {len(df)} linha(s) — colunas: {list(df.columns)}")

    except Exception as exc:
        print(f"  [ERRO] {exc}")
        errors.append(name)

print("\n" + "=" * 50)
if errors:
    print(f"FALHOU: {len(errors)} consulta(s)")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
else:
    print("Todas as consultas Athena validadas com sucesso.")
    print("\nPróximo passo: abra dashboard.ipynb no Jupyter Lab")
