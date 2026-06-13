# Evidências de execução — ETL incremental (3.4 do enunciado)

Ambiente: bucket `lab-classicmodels-gustavotironi-20260610`, job
`classicmodels-etl-job`, banco `classicmodels` (RDS), pipeline
`classicmodels_sales` em `etl_watermark`.

Cada ciclo = `simulate_new_orders` → Glue incremental → validação mínima
(1. Glue run `SUCCEEDED`, 2. novos objetos em `fact_orders/order_year=…/order_month=…/`,
3. watermark avançou, 4. Athena `COUNT(*)`, 5. `sales_amount` consistente).

---

## Ciclo 1

### 1. `simulate_new_orders`

```
$ python simulator/simulate_new_orders.py --count 5 --seed 99
Data de referência (baseline): 2026-05-18
  [ok] orderNumber=10431 date=2026-05-19 ...
  [ok] orderNumber=10432 date=2026-05-20 ...
  [ok] orderNumber=10433 date=2026-05-22 ...
  [ok] orderNumber=10434 date=2026-05-23 ...
  [ok] orderNumber=10435 date=2026-05-25 ...
RESUMO
  Pedidos criados: 5 (10431–10435)
  Faixa de datas: 2026-05-19 → 2026-05-25
  Total linhas em orderdetails: 11
```

`baseline = 2026-05-18` é exatamente o `last_processed_order_date` deixado
pelo ciclo incremental anterior — todos os pedidos novos têm `orderDate`
posterior a esse valor.

### 2. Job Glue incremental

- Job Run ID: `jr_8f40761cbdf6734c7a85787a8c0e4bb2942bb185201dbea5067c6e5fc000d9a1` → **SUCCEEDED**
- Log do job confirma o filtro pelo watermark:
  ```
  reading orders delta (orderDate > 2026-05-18) ...
  read orders delta rows=5
  ```

## Ciclo 2 (segunda execução — 3.4.2)

### 1. `simulate_new_orders`

```
$ python simulator/simulate_new_orders.py --count 5 --seed 7
Data de referência (baseline): 2026-05-25
  [ok] orderNumber=10436 date=2026-05-26 customerNumber=198 details=1
  [ok] orderNumber=10437 date=2026-05-27 customerNumber=471 details=3
  [ok] orderNumber=10438 date=2026-05-28 customerNumber=219 details=1
  [ok] orderNumber=10439 date=2026-05-29 customerNumber=409 details=1
  [ok] orderNumber=10440 date=2026-06-01 customerNumber=256 details=3
RESUMO
  Pedidos criados: 5
  IDs: [10436, 10437, 10438, 10439, 10440]
  Faixa de datas: 2026-05-26 → 2026-06-01
  Total linhas em orderdetails: 9
```

`baseline = 2026-05-25` = watermark deixado pelo Ciclo 1 → confirma que
**apenas pedidos com `orderDate` acima do watermark anterior** entram neste
ciclo. Desta vez a faixa cruza para junho/2026, criando uma partição nova
(`order_month=6`).

### 2. Job Glue incremental

- Job Run ID: `jr_b31f2cf3ff4ce28ba966b1a5464a5db795185abc97411bac6522699e1eefa228` → **SUCCEEDED**

### 3. Validação mínima (`src/validate_etl_incremental.py`)

```
$ python src/validate_etl_incremental.py --prev-watermark 2026-05-25 --order-year 2026 --order-month 5
=== 1. Glue job status ===
  [ok]   Job jr_b31f2cf3ff4ce28ba966b1a5464a5db795185abc97411bac6522699e1eefa228 -> SUCCEEDED
=== 2. Objetos em fact_orders/order_year=2026/order_month=5/ ===
  [ok]   7 arquivo(s) parquet em s3://lab-classicmodels-gustavotironi-20260610/analytics/fact_orders/order_year=2026/order_month=5/
=== 3. etl_watermark avançou ===
  [ok]   last_processed_order_date: 2026-05-25 -> 2026-06-01
=== 4. Athena: COUNT(*) FROM fact_orders WHERE order_year = 2026 ===
  [ok]   SELECT COUNT(*) AS n FROM fact_orders WHERE order_year = 2026 AND order_month = 5 -> 24 linha(s)
=== 5. Regra sales_amount == quantity_ordered * price_each (partição nova) ===
  [ok]   sales_amount consistente em 24 registro(s)
RESULTADO: PASSOU — todas as verificações ok

$ python src/validate_etl_incremental.py --prev-watermark 2026-05-25 --order-year 2026 --order-month 6
=== 1. Glue job status ===
  [ok]   Job jr_b31f2cf3ff4ce28ba966b1a5464a5db795185abc97411bac6522699e1eefa228 -> SUCCEEDED
=== 2. Objetos em fact_orders/order_year=2026/order_month=6/ ===
  [ok]   1 arquivo(s) parquet em s3://lab-classicmodels-gustavotironi-20260610/analytics/fact_orders/order_year=2026/order_month=6/
=== 3. etl_watermark avançou ===
  [ok]   last_processed_order_date: 2026-05-25 -> 2026-06-01
=== 4. Athena: COUNT(*) FROM fact_orders WHERE order_year = 2026 ===
  [ok]   SELECT COUNT(*) AS n FROM fact_orders WHERE order_year = 2026 AND order_month = 6 -> 3 linha(s)
=== 5. Regra sales_amount == quantity_ordered * price_each (partição nova) ===
  [ok]   sales_amount consistente em 3 registro(s)
RESULTADO: PASSOU — todas as verificações ok
```

### Linhas novas em `fact_orders` coerentes com os pedidos simulados

| Partição | Antes (Ciclo 1) | `orderdetails` novos no Ciclo 2 | Depois (Athena `COUNT(*)`) |
|---|---|---|---|
| `order_year=2026/order_month=5` | 18 (= 7 do ciclo anterior ao Ciclo 1 + 11 do Ciclo 1) | + 6 (pedidos 10436–10439) | **24** ✅ |
| `order_year=2026/order_month=6` | 0 (partição não existia) | + 3 (pedido 10440) | **3** ✅ |

`18 + 6 = 24` e `0 + 3 = 3` — o número de linhas novas bate exatamente com os
9 registros de `orderdetails` gerados pelo simulador, sem duplicação (merge
incremental por `(order_id, product_id)`) e sem perda.

---

## EventBridge (3.4.3)

- `terraform/eventbridge.tf` define `aws_scheduler_schedule.weekly_etl`
  (EventBridge Scheduler, target `arn:aws:scheduler:::aws-sdk:glue:startJobRun`,
  `role_arn = local.glue_role_arn` / LabRole).
- Schedule trocado temporariamente para `rate(1 minute)` para teste de
  disparo automático:
  - **Job Run ID: `jr_c6216569f0bb19c5df28b785f6831b1007ec6e0fd1a8cccd71c026f88788b6a8`**
  - Iniciado 17:41:00 UTC, **SUCCEEDED** 17:43:56 UTC.