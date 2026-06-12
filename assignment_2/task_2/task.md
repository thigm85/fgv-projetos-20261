# Task Tracker: Assignment 2 - Task 2 (Incremental ETL)

- [x] **Parte 0: Git**
  - [x] Criar e mudar para a nova branch: `assignment2/task_2/grupo_1/gustavo_bianchi`

- [x] **Parte 1: Base e Estrutura Inicial**
  - [x] Criar a pasta `assignment_2/task_2/grupo_1/gustavo_bianchi`
  - [x] Copiar os arquivos base do A1T2 (`main.tf`, `variables.tf`, `etl_script.py`, etc.)
  - [x] Commit: `feat(A2T2): copia estrutura base do ETL da Task 2 do Assignment 1`

- [x] **Parte 2: Infraestrutura do Agendamento e Catálogo (Terraform)**
  - [x] Adicionar `aws_cloudwatch_event_rule` (cron trigger semanal) no `main.tf`
  - [x] Adicionar `aws_cloudwatch_event_target` apontando para o Glue Job
  - [x] Atualizar permissões IAM para o EventBridge ( `glue:StartJobRun` )
  - [x] Atualizar o catálogo do Glue no Terraform (ou via AWS Glue Crawler) para declarar as partition keys `order_year` e `order_month` na tabela `fact_orders`
  - [x] Adicionar AWS Secrets Manager ou variáveis sensíveis no TF para a credencial JDBC (Boas práticas recomendadas no item 3.1.3)
  - [x] Commit: `feat(A2T2): adiciona EventBridge e particionamento no Glue Catalog via Terraform`

- [x] **Parte 3: Extração Incremental e Watermark (Glue PySpark)**
  - [x] Ler tabela `etl_watermark` filtrando por `pipeline_name = 'classicmodels_sales'`
  - [x] Lidar com o caso de primeira execução (`NEVER_RUN` / data muito antiga)
  - [x] Modificar extrações via JDBC (apenas via JDBC)
  - [x] Aplicar filtro `orders.orderDate > last_processed_order_date`
  - [x] Commit: `feat(A2T2): adiciona leitura de watermark e extração incremental via JDBC`

- [x] **Parte 4: Particionamento, Merge e Watermark (Glue PySpark)**
  - [x] Adicionar `order_year` e `order_month` na `fact_orders` (derivado da `dim_dates` ou `orderDate`)
  - [x] Gravar `fact_orders` particionado (S3 Hive-style: `order_year=.../order_month=...`)
  - [x] Aplicar estratégia de merge/append na fato usando chaves de negócio (`order_id`, `product_id`)
  - [x] Sobrescrever prefixo `dim_*` (Opção A) ou fazer merge incremental nas dimensões (Opção B)
  - [x] Atualizar `etl_watermark` (Em Sucesso: MAX(orderDate), now() e 'SUCCEEDED'. Em falha: não avança a data e 'FAILED')
  - [x] Commit: `feat(A2T2): adiciona particionamento, merge em S3 e atualizacao restrita do watermark`

- [ ] **Parte 5: Testes e Evidências**
  - [ ] Executar pipeline com simulação de novos pedidos (`simulate_new_orders.py`) duas vezes
  - [ ] Validar partições no S3 (`fact_orders/order_year=…/order_month=…/`) e query no Athena
  - [ ] Comprovar que métrica `sales_amount = quantity_ordered * price_each` se mantém correta no delta
  - [ ] Documentar em `evidence/` ou no `README` o filtro atuando e o disparo via EventBridge
  - [ ] Commit: `docs(A2T2): adiciona evidencias de execucao incremental e EventBridge`
