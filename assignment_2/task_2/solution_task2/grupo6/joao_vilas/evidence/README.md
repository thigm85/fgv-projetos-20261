# Evidências de execução (Task 2)

Coloque aqui os artefatos das **duas** execuções do ciclo completo (requisito 3.4) e do
disparo via EventBridge (3.4.3). Sugestão de conteúdo:

- `run1_full_glue_log.txt` — log do Glue da 1ª execução (modo FULL).
- `run2_incremental_glue_log.txt` — log da 2ª execução (modo INCREMENTAL), evidenciando:
  - `modo=INCREMENTAL` e `pedidos no escopo deste run` igual ao nº de pedidos simulados;
  - apenas pedidos com `orderDate` acima do watermark anterior foram extraídos;
  - nº de linhas novas em `fact_orders` coerente com os pedidos simulados.
- `watermark_before_after.txt` — `SELECT * FROM etl_watermark` antes/depois (data avançou).
- `s3_partitions.txt` — `aws s3 ls --recursive .../fact_orders/`.
- `athena_count.png` — `SELECT COUNT(*) FROM fact_orders WHERE order_year = 2003`.
- `eventbridge_job_run_id.txt` — Job Run ID disparado pela Lambda/EventBridge.

Estes arquivos não são versionados por padrão (são saídas de runtime); commitar é opcional.
