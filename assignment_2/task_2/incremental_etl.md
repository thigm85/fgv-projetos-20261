# Assignment 2 - Task 2: ETL incremental, particoes e agendamento

## Objetivo

Evoluir o pipeline do Assignment 1 para processar apenas pedidos novos desde o watermark da Task 1, gravar `fact_orders` particionado no S3 e agendar a execucao com EventBridge e AWS Glue.

## Arquitetura

```text
RDS classicmodels
  -> Glue Job incremental via JDBC
  -> S3 analytics/fact_orders/order_year=YYYY/order_month=MM/
  -> Glue Catalog / Athena

etl_watermark
  -> lido no inicio do job
  -> atualizado somente apos sucesso

EventBridge
  -> Glue Workflow
  -> Glue Job
```

## Requisitos atendidos

1. O Glue job le `etl_watermark` para `pipeline_name = 'classicmodels_sales'`.
2. A extracao JDBC filtra `orders.orderDate > last_processed_order_date`.
3. As dimensoes sao reprocessadas em overwrite completo, apropriado para o volume de laboratorio.
4. A fato usa merge por particao afetada e chave de negocio (`order_id`, `product_id`).
5. `fact_orders` e gravada com particoes `order_year` e `order_month`.
6. O Glue Catalog declara `order_year` e `order_month` como partition keys.
7. O watermark so avanca para `MAX(orderDate)` quando o job termina com sucesso.
8. Em falha, `last_run_status` vira `FAILED` sem avancar a data processada.
9. Terraform declara RDS, S3, Glue Job, Glue Catalog, Glue Workflow e EventBridge com prefixos configuraveis para esta entrega.

## Validacao sugerida

```sql
SELECT COUNT(*)
FROM fact_orders
WHERE order_year = 2026
  AND order_month = 6;
```

```sql
SELECT order_id, product_id, quantity_ordered, price_each, sales_amount
FROM fact_orders
WHERE ABS(sales_amount - quantity_ordered * price_each) > 0.01;
```

A segunda consulta deve retornar zero linhas.
