# Assignment 2 — Task 2: ETL incremental, partições e agendamento

## 1 — Introdução

Na [Task 1](../task_1/incremental_source.md) você preparou o OLTP para receber pedidos novos e registrou um **watermark** em `etl_watermark`. Agora você evolui o pipeline do [Assignment 1 — Task 2](../../assignment_1/task_2/data_pipeline.md) para:

1. Processar **apenas o delta** desde o watermark.
2. Gravar `fact_orders` **particionado** no S3.
3. **Agendar** execuções automáticas com Terraform (Amazon EventBridge → AWS Glue).

O contrato do star schema (nomes de tabelas e colunas) permanece o do Assignment 1.

## 2 — Arquitetura alvo

```text
┌─────────────┐     watermark      ┌──────────────┐
│ RDS         │ ◄──────────────────│ etl_watermark│
│ classicmodels│                    └──────────────┘
└──────┬──────┘
       │ JDBC (filtro orderDate > watermark)
       ▼
┌──────────────┐     Parquet        ┌─────────────────────────────┐
│ Glue Job     │ ─────────────────► │ S3 analytics/               │
│ (incremental)│                    │  fact_orders/order_year=…/  │
└──────┬───────┘                    │  dim_*/ …                   │
       │                            └──────────────┬──────────────┘
       │ atualiza watermark                         │
       ▼                                            ▼
 etl_watermark                              Glue Catalog / Athena

┌──────────────┐
│ EventBridge  │──cron──► StartGlueJob (Terraform)
└──────────────┘
```

## 3 — Task 2: Requisitos

### 3.1 — Infraestrutura (Terraform)

Todos os recursos **novos ou alterados** desta tarefa devem estar em Terraform (módulo `terraform/` do grupo). No mínimo:


| Recurso                       | Finalidade                                                            |
| ----------------------------- | --------------------------------------------------------------------- |
| `aws_cloudwatch_event_rule`   | Regra cron (sugestão: `cron(0 12 ? * MON *)` — semanal, meio-dia UTC) |
| `aws_cloudwatch_event_target` | Disparo do job Glue existente                                         |
| Permissões IAM                | EventBridge pode invocar Glue (`glue:StartJobRun` na role adequada)   |
| Ajustes no catálogo Glue      | Partições de `fact_orders` visíveis ao Athena                         |


**3.1.1.** Caminhos de arquivos referenciados em `aws_s3_object` (script do job) devem existir no repositório entregue — use `path.module` ou caminho relativo ao root da solução, nunca um path que só existe na máquina de um integrante.

**3.1.2.** Em laboratórios com `LabRole` fixa, documente no README qual role o EventBridge usa e quais permissões foram anexadas (policy inline ou anexo à `LabRole`).

**3.1.3.** (Recomendado) Armazene credenciais JDBC em **AWS Secrets Manager** e referencie no Glue Connection. Se o lab não permitir Secrets Manager, use variáveis Terraform sensíveis + `.gitignore` — **nunca** commite senhas.

### 3.2 — Lógica incremental no Glue

Evolua o job Glue (PySpark) para o modo incremental:

**3.2.1. Leitura do watermark**

- No início do job, leia `etl_watermark` para `pipeline_name = 'classicmodels_sales'`.
- Obtenha `last_processed_order_date` (trate `NEVER_RUN` / primeira execução incremental após A1 conforme documentado no README).

**3.2.2. Extração JDBC filtrada**

- Extraia de `orders`, `orderdetails`, `customers`, `products`, `productlines`, `offices` (e demais tabelas necessárias ao star schema) **via Glue JDBC**, não via arquivos locais.
- Filtre pedidos com `orders.orderDate > last_processed_order_date` (ajuste se usar timestamp; documente o tipo).
- Para dimensões, você pode:
  - **Opção A (mínima):** reprocessar dimensões completas a cada run (aceitável em lab com volume pequeno), **ou**
  - **Opção B (bônus):** atualizar apenas dimensões afetadas pelos novos pedidos.

**3.2.3. Transformação**

- Mantenha o star schema do A1 (`fact_orders`, `dim_`*) com os mesmos nomes de colunas obrigatórios.
- Adicione em `fact_orders` as colunas de partição (ver 3.3), derivadas de `dim_dates.year` e `dim_dates.month` (ou de `orders.orderDate`).

**3.2.4. Load / merge na fato**

- Faça **merge incremental** em `fact_orders`:
  - Chave de negócio: (`order_id`, `product_id`) — alinhada ao grão da fato do A1.
  - Estratégia aceita: ler partições afetadas, remover chaves duplicadas do delta, append dos novos registros; ou `dynamicFrame` com overwrite de partições tocadas.
- Dimensões: overwrite completo do prefixo `dim_`* (Opção A) ou merge documentado (Opção B).

**3.2.5. Atualização do watermark**

- Somente se o job terminar com sucesso lógico (sem exceção):
  - `last_processed_order_date = MAX(orderDate)` processado neste run.
  - `last_run_at = UTC now`.
  - `last_run_status = 'SUCCEEDED'`.
- Em falha, defina `last_run_status = 'FAILED'` **sem** avançar a data processada.

### 3.3 — Particionamento de `fact_orders`

Grave `fact_orders` no S3 com estrutura de partição Hive-style:

```text
s3://<bucket>/analytics/fact_orders/order_year=YYYY/order_month=MM/part-….parquet
```

**Colunas de partição (obrigatórias no catálogo Glue):**


| Coluna        | Tipo  | Origem               |
| ------------- | ----- | -------------------- |
| `order_year`  | `int` | Ano do pedido        |
| `order_month` | `int` | Mês do pedido (1–12) |


Atualize a tabela externa no Glue Catalog para declarar `order_year` e `order_month` como **partition keys**. Garanta que consultas Athena com filtro de partição funcionem.

### 3.4 — Execução e evidência

**3.4.1.** Execute manualmente pelo menos **duas** vezes o ciclo completo:

1. `simulate_new_orders` (Task 1)
2. Job Glue incremental
3. Validação mínima (pode ser o script da Task 3 em versão rascunho)

**3.4.2.** Na segunda execução, documente (no README ou em `evidence/`) que:

- Apenas pedidos com `orderDate` acima do watermark anterior foram extraídos.
- O número de linhas novas em `fact_orders` é coerente com os pedidos simulados.

**3.4.3.** Dispare o job via EventBridge pelo menos uma vez e registre o **Job Run ID** do Glue.

## 4 — Critérios mínimos de conclusão da Task 2

1. Job Glue incremental via JDBC com filtro por watermark.
2. `fact_orders` particionado por `order_year` / `order_month` no S3 e no catálogo Glue.
3. Watermark atualizado apenas após sucesso.
4. EventBridge + target declarados em Terraform (ou fallback documentado se IAM bloquear).
5. Mantidos os critérios do A1 para schema (`fact_orders`, `dim_`*, `sales_amount = quantity_ordered * price_each`).
6. Nenhuma extração principal via CSV local.

## 5 — Validação técnica sugerida (pré-Task 3)

Antes de entregar a Task 2, confira:


| #   | Verificação                                                                    |
| --- | ------------------------------------------------------------------------------ |
| 1   | Glue run `SUCCEEDED`                                                           |
| 2   | Novos objetos sob `fact_orders/order_year=…/order_month=…/`                    |
| 3   | `etl_watermark.last_processed_order_date` avançou                              |
| 4   | Athena: `SELECT COUNT(*) FROM fact_orders WHERE order_year = …` retorna linhas |
| 5   | Regras de `sales_amount` ainda válidas no delta                                |


