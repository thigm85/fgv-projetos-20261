# Evidências — Assignment 2 Task 2

Grupo 5 — Final. Pipeline incremental `classicmodels_sales` sobre RDS `meu-mysql-lab`.

Infra: bucket `grupo5-a2-task2-a42fac44`, job `grupo5-a2-task2-incremental-etl`, database Glue `grupo5_a2_task2_analytics`.

## Execução 1

| Campo | Valor |
|-------|-------|
| Data | 2026-06-11 |
| Pedidos simulados (`orderNumber`) | 10426, 10427, 10428, 10429, 10430 (`simulate_new_orders.py`, 5 pedidos) |
| Glue Job Run ID | `jr_308c8e71e703a9ab2263774a08c8344653cd7cf873f9bfb171482e4a993c66b1` |
| Status | SUCCEEDED |
| Duração | 292 s |
| Watermark antes | 2005-05-31 |
| Watermark depois | 2026-06-03 |
| Linhas novas em `fact_orders` | 5 (1 linha por pedido em `orderdetails`) |
| Partições S3 gravadas | `order_year=2026/order_month=5`, `order_year=2026/order_month=6` |

Validação pós-run (`validate_incremental_source.py`): `last_run_status=SUCCEEDED`, sem pedidos pendentes.

## Execução 2

| Campo | Valor |
|-------|-------|
| Data | 2026-06-11 |
| Pedidos simulados (`orderNumber`) | 10431, 10432, 10433, 10434, 10435 |
| Faixa `orderDate` simulada | 2026-06-04 .. 2026-06-10 |
| Glue Job Run ID | `jr_97d5c9ce86caf9b93790965760e58f01d28554f82054aa397aed10b38096e29c` |
| Status | SUCCEEDED |
| Duração | 136 s |
| Watermark antes | 2026-06-03 |
| Watermark depois | 2026-06-10 |
| Linhas novas em `fact_orders` | 5 |
| Confirmação: só `orderDate > watermark anterior` | Sim — job leu watermark `2026-06-03` e processou apenas os 5 pedidos com datas posteriores |

Log: `Pedidos novos encontrados: 5`. Partição atualizada: `order_year=2026/order_month=6` (fallback de merge em arquivo Parquet antigo; delta regravado com sucesso).

Validação pós-run: `last_processed_order_date=2026-06-10`, `last_run_status=SUCCEEDED`, integridade `orderdetails` OK.

## EventBridge

| Campo | Valor |
|-------|-------|
| Regra | `grupo5-a2-task2-glue-schedule` |
| Workflow alvo | `grupo5-a2-task2-etl-workflow` |
| Cron (UTC) | `cron(0 12 ? * MON *)` |
| Role | `LabRole` |
| Disparo manual testado | Não — agendamento provisionado via Terraform; execuções deste log foram manuais (`aws glue start-job-run`) |

## S3 (amostra)

```text
s3://grupo5-a2-task2-a42fac44/analytics/
  dim_customers/
  dim_products/
  dim_countries/
  dates_dim/
  fact_orders/order_year=2026/order_month=5/
  fact_orders/order_year=2026/order_month=6/
```

## Athena (exemplo)

```sql
SELECT order_year, order_month, COUNT(*) AS n
FROM grupo5_a2_task2_analytics.fact_orders
GROUP BY order_year, order_month
ORDER BY order_year, order_month;
```

Resultado esperado após os dois ciclos: linhas nas partições `2026/5` e `2026/6` (volume pequeno, ~10 linhas no total conforme merges).