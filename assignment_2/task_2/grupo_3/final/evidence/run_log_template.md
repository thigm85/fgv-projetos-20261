# Evidence - Assignment 2 Task 2

Registro das execucoes realizadas em AWS para validar o ETL incremental do `classicmodels`.

## Ambiente

- Data/hora: 2026-06-11, entre 22:43 e 22:50, horario America/Sao_Paulo
- Regiao AWS: `us-east-1`
- Bucket: `classicmodels-etl-098150390570-us-east-1`
- Glue database: `classicmodels_analytics`
- Glue job: `classicmodels-incremental-etl`
- EventBridge schedule: `classicmodels-incremental-etl-weekly`
- Role Glue: `LabRole` / role configurada no `terraform.tfvars`
- Role EventBridge: `LabRole` / role configurada no `terraform.tfvars`

## Execucao 1

- Watermark antes: `2005-05-31`
- Comando simulate_new_orders: `python scripts/simulate_new_orders.py --count 5 --seed 42`
- Pedidos criados: `10426`, `10427`, `10428`, `10429`, `10430`
- Faixa de orderDate: `2005-06-01` a `2005-06-05`
- Linhas em orderdetails criadas: `5`
- Validacao antes do Glue:
  - `max_order_date`: `2005-06-05`
  - `pedidos_pendentes`: `5`
  - `pedidos_pendentes_sem_orderdetails`: `0`
- Glue Job Run ID: `jr_8ea8991c66e003d4548599a13efe60bd80daf92c193db64062da09736faa8ce3`
- Status do Glue: `SUCCEEDED`
- Inicio do Glue: `2026-06-11T22:43:03.416000-03:00`
- Fim do Glue: `2026-06-11T22:45:15.248000-03:00`
- Watermark depois: `2005-06-05`
- Particoes S3 criadas/atualizadas:
  - `s3://classicmodels-etl-098150390570-us-east-1/analytics/fact_orders/order_year=2005/order_month=6/part-00000-e072d227-5fff-4df7-9f80-23da234f875b.c000.snappy.parquet`
- Athena COUNT na particao: nao registrado nesta evidencia
- Athena invalid_sales_amount: nao registrado nesta evidencia

## Execucao 2

- Watermark antes: `2005-06-05`
- Comando simulate_new_orders: `python scripts/simulate_new_orders.py --count 3 --seed 99`
- Pedidos criados: `10431`, `10432`, `10433`
- Faixa de orderDate: `2005-06-06` a `2005-06-08`
- Linhas em orderdetails criadas: `3`
- Validacao antes do Glue:
  - `max_order_date`: `2005-06-08`
  - `pedidos_pendentes`: `3`
  - `pedidos_pendentes_sem_orderdetails`: `0`
- Glue Job Run ID: `jr_46881bbd02b390c550e0d634b00f8d5773da41f58b9954da886d808818360365`
- Status do Glue: `SUCCEEDED`
- Inicio do Glue: `2026-06-11T22:47:39.302000-03:00`
- Fim do Glue: `2026-06-11T22:49:50.930000-03:00`
- Watermark depois: `2005-06-08`
- Validacao depois do Glue:
  - `max_order_date`: `2005-06-08`
  - `pedidos_pendentes`: `0`
  - `pedidos_pendentes_sem_orderdetails`: `0`
- Particoes S3 criadas/atualizadas:
  - `s3://classicmodels-etl-098150390570-us-east-1/analytics/fact_orders/order_year=2005/order_month=6/part-00001-89dc0174-8d50-4950-8d4a-dc7eb3b8b25c.c000.snappy.parquet`
- Athena COUNT na particao: nao registrado nesta evidencia
- Athena invalid_sales_amount: nao registrado nesta evidencia
- Evidencia de delta: a segunda simulacao criou apenas pedidos com `orderDate` maior que o watermark anterior (`2005-06-05`), na faixa `2005-06-06` a `2005-06-08`. A validacao antes do Glue indicou `3` pedidos pendentes, coerente com os `3` pedidos simulados.

## EventBridge

- Metodo de disparo: agendamento declarado pelo Terraform em `aws_scheduler_schedule.weekly_incremental_etl`
- API chamada pelo schedule: `glue:startJobRun`
- Expressao configurada: `cron(0 12 ? * MON *)`
- Job Run ID iniciado pelo EventBridge Scheduler: nao registrado nesta evidencia
- Horario UTC do disparo: nao registrado nesta evidencia
- Status: nao registrado nesta evidencia

## Conclusao da evidencia

As duas execucoes manuais do Glue terminaram com `SUCCEEDED`. A primeira processou `5` pedidos acima do watermark `2005-05-31` e a segunda processou `3` pedidos acima do watermark `2005-06-05`. Em ambas, os arquivos Parquet foram gerados na particao Hive-style:

```text
analytics/fact_orders/order_year=2005/order_month=6/
```

As validacoes Athena e o Job Run ID iniciado diretamente pelo EventBridge Scheduler nao foram registrados neste arquivo. A evidencia principal registrada cobre as duas execucoes incrementais manuais exigidas para demonstrar filtro por watermark, avanco do watermark e escrita particionada em S3.
