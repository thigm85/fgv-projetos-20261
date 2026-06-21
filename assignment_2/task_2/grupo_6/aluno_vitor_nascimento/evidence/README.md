# Evidências de Execução — Task 2

Esta pasta contém as evidências para a conclusão da Task 2 do Assignment 2, conforme especificado na seção 3.4.2 das instruções.

---

### 1. Ingestão Incremental e Filtro por Watermark
- **Baseline Histórico**: Na primeira execução do pipeline (baseline), a tabela `etl_watermark` na origem RDS foi consultada e a data de watermark inicial obtida foi `2005-05-31` (a data máxima de pedido da base histórica `classicmodels`). Como não haviam pedidos adicionais inseridos além do histórico, a contagem de registros delta retornou zero: `Numero de novas ordens encontradas: 0`.
- **Detecção de Novos Pedidos**: Após rodar a simulação com `python scripts/simulate_new_orders.py --count 10 --seed 42`, foram criados 10 pedidos fictícios com datas estritamente posteriores ao watermark. O script `validate_incremental_source.py` detectou os novos pedidos pendentes na origem.
- **Extração Incremental**: Na segunda execução do Glue Job, a leitura de watermark identificou `2005-05-31` e filtrou a tabela de origem `orders` aplicando `orderDate > 2005-05-31`. Os logs do driver do Glue registraram com sucesso: `Numero de novas ordens encontradas: 10`. Apenas os 10 novos pedidos simulados foram transferidos.

---

### 2. Coerência na Contagem de Registros
- **Merge e Deduplicação no S3**:
  - O Glue Job executou o merge entre os dados existentes no S3 e o delta de 10 pedidos. A validação via `validate_etl.py` comprovou que o número de registros na tabela fato pós-gravação refletiu o acréscimo exato de novos itens de pedido simulados, sem registros duplicados ou chaves nulas na partição correspondente (ano 2026).
  - A estrutura do S3 foi devidamente estruturada no padrão Hive:
    `s3://<bucket-name>/transformed_data/fact_orders/order_year=2026/order_month=06/part-....parquet`

---

### 3. Agendamento via EventBridge e Glue Workflow
- **Disparo Automático**: O Glue Job foi executado de forma automática e integrada através da regra do EventBridge configurada via Terraform. O EventBridge acionou o Glue Workflow (`rds-to-s3-star-schema-workflow`), que iniciou o Glue Job, finalizado com status `SUCCEEDED`.
- **Job Run ID de Exemplo**:
  - ID da Execução: `jr_c3ee63faea5becac7516f4da954eebd09474ea2461d91e73ef95a4993f59d6dc` (ou posterior)
