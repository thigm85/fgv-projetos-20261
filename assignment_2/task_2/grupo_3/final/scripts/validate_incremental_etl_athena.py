import argparse
import sys
import time

import boto3


def parse_args():
    parser = argparse.ArgumentParser(description="Valida a carga incremental no Athena.")
    parser.add_argument("--database", default="classicmodels_analytics", help="Glue/Athena database.")
    parser.add_argument("--output", required=True, help="S3 output para resultados do Athena.")
    parser.add_argument("--region", default="us-east-1", help="Regiao AWS.")
    parser.add_argument("--order-year", type=int, required=True, help="Particao order_year a validar.")
    parser.add_argument("--order-month", type=int, required=True, help="Particao order_month a validar.")
    return parser.parse_args()


def wait_query(athena, query_execution_id):
    while True:
        response = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = response["QueryExecution"]["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return state, response["QueryExecution"]["Status"].get("StateChangeReason", "")
        time.sleep(2)


def run_query(athena, database, output, query):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output},
    )
    query_execution_id = response["QueryExecutionId"]
    state, reason = wait_query(athena, query_execution_id)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena query {query_execution_id} terminou em {state}: {reason}")

    result = athena.get_query_results(QueryExecutionId=query_execution_id)
    rows = result["ResultSet"]["Rows"]
    return query_execution_id, rows[1]["Data"][0].get("VarCharValue") if len(rows) > 1 else None


def main():
    args = parse_args()
    athena = boto3.client("athena", region_name=args.region)

    count_query = f"""
        SELECT COUNT(*) AS rows_in_partition
        FROM fact_orders
        WHERE order_year = {args.order_year}
          AND order_month = {args.order_month}
    """
    invalid_sales_query = f"""
        SELECT COUNT(*) AS invalid_sales_amount
        FROM fact_orders
        WHERE order_year = {args.order_year}
          AND order_month = {args.order_month}
          AND ABS(sales_amount - quantity_ordered * price_each) > 0.0001
    """

    count_id, rows_in_partition = run_query(athena, args.database, args.output, count_query)
    invalid_id, invalid_sales_amount = run_query(athena, args.database, args.output, invalid_sales_query)

    rows_in_partition = int(rows_in_partition or 0)
    invalid_sales_amount = int(invalid_sales_amount or 0)

    print("Validacao Athena incremental:")
    print(f"- count_query_execution_id: {count_id}")
    print(f"- invalid_sales_query_execution_id: {invalid_id}")
    print(f"- order_year: {args.order_year}")
    print(f"- order_month: {args.order_month}")
    print(f"- rows_in_partition: {rows_in_partition}")
    print(f"- invalid_sales_amount: {invalid_sales_amount}")

    if rows_in_partition <= 0:
        print("[ERRO] Particao validada nao possui linhas.")
        return 1
    if invalid_sales_amount != 0:
        print("[ERRO] Ha linhas com sales_amount inconsistente.")
        return 1

    print("Validacao concluida com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
