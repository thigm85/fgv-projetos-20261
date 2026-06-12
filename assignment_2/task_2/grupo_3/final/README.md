# Assignment 2 - Task 2: ETL incremental, particionamento e agendamento

Esta entrega implementa a evolucao incremental do pipeline analitico do banco `classicmodels`. A solucao parte do modelo estrela produzido no Assignment 1 e adiciona controle de watermark no RDS, extracao JDBC filtrada, escrita particionada da tabela fato em S3, catalogacao para Athena e agendamento automatico via Amazon EventBridge.

O objetivo e processar somente pedidos novos desde a ultima execucao bem-sucedida, mantendo o contrato do star schema usado anteriormente.

## Arquitetura

```text
RDS MySQL classicmodels
  |- orders, orderdetails, customers, products, productlines
  |- etl_watermark
        |
        | JDBC com filtro orders.orderDate > watermark
        v
AWS Glue Job incremental
        |
        | Parquet
        v
S3 analytics/
  |- dim_customers/
  |- dim_products/
  |- dim_dates/
  |- dim_countries/
  |- fact_orders/order_year=YYYY/order_month=MM/
        |
        v
Glue Catalog / Athena

EventBridge Scheduler -> glue:startJobRun
```

## Componentes entregues

```text
final/
|- README.md
|- requirements.txt
|- evidence/
|  |- run_log_template.md
|- scripts/
|  |- glue_incremental_etl.py
|  |- init_watermark.py
|  |- simulate_new_orders.py
|  |- validate_incremental_source.py
|  |- validate_incremental_etl_athena.py
|  |- db.py
|  |- env_loader.py
|  |- .env.example
|- terraform/
|  |- main.tf
|  |- variables.tf
|  |- outputs.tf
|  |- terraform.tfvars.example
```

## Logica incremental

O job principal esta em `scripts/glue_incremental_etl.py`.

No inicio da execucao, o Glue le a tabela `etl_watermark` no RDS para o registro:

```text
pipeline_name = classicmodels_sales
```

A coluna usada como watermark e:

```text
last_processed_order_date
```

Com esse valor, o job extrai do MySQL apenas pedidos novos:

```sql
orders.orderDate > last_processed_order_date
```

As tabelas de origem usadas pelo ETL sao lidas via JDBC:

```text
orders
orderdetails
customers
products
productlines
```

As dimensoes sao reprocessadas por overwrite completo a cada execucao. Essa foi a estrategia minima escolhida para o laboratorio, pois o volume do `classicmodels` e pequeno e a abordagem simplifica a consistencia das dimensoes.

A fato `fact_orders` e atualizada incrementalmente. O grao permanece uma linha por item de pedido, com chave de negocio:

```text
(order_id, product_id)
```

Para evitar duplicidade, o job le as particoes afetadas pelo delta, remove registros existentes com a mesma chave de negocio e regrava as particoes tocadas com os registros antigos restantes mais os novos registros.

## Star schema mantido

A entrega preserva as tabelas analiticas do Assignment 1:

```text
dim_customers
dim_products
dim_dates
dim_countries
fact_orders
```

A regra de negocio de vendas tambem foi mantida:

```text
sales_amount = quantity_ordered * price_each
```

O job possui uma checagem de qualidade para garantir que `sales_amount` continua coerente no delta processado.

## Particionamento da fato

A tabela `fact_orders` e gravada em S3 no prefixo:

```text
s3://<bucket>/analytics/fact_orders/
```

Com particionamento Hive-style:

```text
s3://<bucket>/analytics/fact_orders/order_year=YYYY/order_month=MM/
```

As colunas de particao sao derivadas de `orders.orderDate`:

```text
order_year  int
order_month int
```

No Terraform, a tabela `fact_orders` e declarada no Glue Catalog com `order_year` e `order_month` como `partition_keys`. Tambem foi configurada partition projection para permitir consultas no Athena filtrando as particoes sem depender de reparo manual da tabela.

## Watermark

A tabela `etl_watermark` segue o contrato da Task 1:

```text
pipeline_name
last_processed_order_date
last_run_at
last_run_status
```

Comportamento implementado:

```text
SUCCEEDED com delta:
  last_processed_order_date recebe MAX(orderDate) processado
  last_run_at recebe o timestamp UTC da execucao
  last_run_status recebe SUCCEEDED

SUCCEEDED sem delta:
  last_processed_order_date permanece igual
  last_run_at e atualizado
  last_run_status recebe SUCCEEDED

FAILED:
  last_processed_order_date nao avanca
  last_run_at e atualizado
  last_run_status recebe FAILED
```

## Infraestrutura

A infraestrutura da Task 2 esta declarada em `terraform/`.

Recursos principais:

```text
aws_s3_bucket
aws_vpc_endpoint para acesso S3 a partir da subnet usada pelo Glue
aws_s3_object para publicar o script Glue
aws_glue_connection
aws_glue_job
aws_glue_catalog_database
aws_glue_catalog_table para dimensoes e fato
aws_scheduler_schedule
aws_iam_role / aws_iam_role_policy quando a conta permite criacao de IAM
```

O upload do script Glue usa:

```hcl
source = "${path.module}/../scripts/glue_incremental_etl.py"
```

Assim, o Terraform nao depende de caminhos absolutos da maquina de nenhum integrante.

Como o Glue executa dentro da VPC/subnet configurada para acessar o RDS, a subnet tambem precisa ter caminho para o S3. A entrega declara um Gateway VPC Endpoint para S3 quando `glue_vpc_id` e `glue_route_table_ids` sao informados no `terraform.tfvars`. Esse endpoint evita falhas de execucao do Glue por falta de NAT Gateway ou S3 endpoint.

Em ambientes AWS Academy, a entrega permite usar uma role existente, como `LabRole`, por meio das variaveis:

```hcl
existing_glue_role_arn
existing_glue_role_name
existing_eventbridge_role_arn
```

## Agendamento

O agendamento e feito com Amazon EventBridge Scheduler chamando a API `glue:startJobRun` para iniciar o Glue Job incremental.

Expressao padrao:

```text
cron(0 12 ? * MON *)
```

Isso agenda uma execucao semanal, toda segunda-feira ao meio-dia UTC. O valor pode ser alterado pela variavel Terraform:

```hcl
eventbridge_schedule_expression
```

## Configuracao esperada para reproducao

As credenciais AWS e a senha do RDS nao sao versionadas. Para reproduzir a execucao, elas devem ser fornecidas por variaveis de ambiente.

Credenciais AWS temporarias do lab:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_DEFAULT_REGION="us-east-1"
```

Senha do RDS usada pelo Terraform:

```bash
export TF_VAR_db_password="..."
```

Variaveis locais usadas pelos scripts Python:

```bash
export DB_HOST="classicmodels-db.cucwxffzjlxv.us-east-1.rds.amazonaws.com"
export DB_PORT="3306"
export DB_USER="admin"
export DB_PASSWORD="..."
export DB_NAME="classicmodels"
```

O arquivo `terraform/terraform.tfvars` deve conter somente dados nao sensiveis ou dados locais ignorados pelo git, como endpoint, subnet, security group e role. Um exemplo esta em `terraform/terraform.tfvars.example`.

## Como validar a entrega

Os comandos abaixo reproduzem a validacao tecnica da solucao.

Preparar origem incremental:

```bash
cd assignment_2/task_2/grupo_3/final
pip install -r requirements.txt
python scripts/init_watermark.py
python scripts/validate_incremental_source.py
```

Provisionar infraestrutura:

```bash
cd terraform
terraform init
terraform fmt
terraform validate
terraform apply
```

Simular dados novos:

```bash
cd ..
python scripts/simulate_new_orders.py --count 5 --seed 42
python scripts/validate_incremental_source.py --require-pending
```

Executar o Glue Job manualmente:

```bash
cd terraform
JOB_NAME=$(terraform output -raw glue_job_name)
aws glue start-job-run --job-name "$JOB_NAME" --region us-east-1
aws glue get-job-runs --job-name "$JOB_NAME" --max-results 1 --region us-east-1
```

Verificar arquivos particionados no S3:

```bash
BUCKET=$(terraform output -raw etl_bucket_name)
aws s3 ls "s3://$BUCKET/analytics/fact_orders/" --recursive --region us-east-1
```

Validar no Athena:

```bash
cd ..
python scripts/validate_incremental_etl_athena.py \
  --database classicmodels_analytics \
  --output "s3://$BUCKET/athena-results/" \
  --order-year 2005 \
  --order-month 6
```

Para validar o comportamento incremental, o ciclo de simulacao e Glue Job deve ser executado pelo menos duas vezes. Na segunda execucao, espera-se que apenas pedidos com `orderDate` maior que o watermark anterior sejam extraidos.

## Resultado validado

A solucao foi executada em AWS em 2026-06-11 e as evidencias detalhadas estao em `evidence/run_log_template.md`.

Resumo das execucoes registradas:

```text
Execucao 1
  watermark antes: 2005-05-31
  pedidos simulados: 10426 a 10430
  orderDate processado: 2005-06-01 a 2005-06-05
  pedidos pendentes antes do Glue: 5
  Glue Job Run ID: jr_8ea8991c66e003d4548599a13efe60bd80daf92c193db64062da09736faa8ce3
  status: SUCCEEDED
  watermark depois: 2005-06-05

Execucao 2
  watermark antes: 2005-06-05
  pedidos simulados: 10431 a 10433
  orderDate processado: 2005-06-06 a 2005-06-08
  pedidos pendentes antes do Glue: 3
  Glue Job Run ID: jr_46881bbd02b390c550e0d634b00f8d5773da41f58b9954da886d808818360365
  status: SUCCEEDED
  watermark depois: 2005-06-08
  pedidos pendentes depois do Glue: 0
```

Arquivos Parquet observados no S3:

```text
s3://classicmodels-etl-098150390570-us-east-1/analytics/fact_orders/order_year=2005/order_month=6/part-00000-e072d227-5fff-4df7-9f80-23da234f875b.c000.snappy.parquet
s3://classicmodels-etl-098150390570-us-east-1/analytics/fact_orders/order_year=2005/order_month=6/part-00001-89dc0174-8d50-4950-8d4a-dc7eb3b8b25c.c000.snappy.parquet
```

O ultimo `validate_incremental_source.py` retornou:

```text
last_processed_order_date: 2005-06-08
max_order_date: 2005-06-08
pedidos_pendentes: 0
pedidos_pendentes_sem_orderdetails: 0
```

## Evidencias

O arquivo `evidence/run_log_template.md` foi incluido para registrar os resultados das execucoes. As evidencias esperadas sao:

```text
Glue Job Run ID
status SUCCEEDED do Glue
watermark antes e depois
pedidos simulados
linhas novas em orderdetails
particoes S3 criadas ou atualizadas
resultado da validacao Athena
Job Run ID iniciado pelo EventBridge
```

Esses registros demonstram que:

```text
1. O delta foi calculado a partir do watermark.
2. A fato foi atualizada sem duplicar a chave (order_id, product_id).
3. A escrita em S3 esta particionada por order_year/order_month.
4. O Glue Catalog permite consulta pelo Athena.
5. O EventBridge consegue iniciar o Glue Job.
```

## Observacoes de seguranca

Senhas e credenciais temporarias nao foram commitadas. O repositorio contem somente `.env.example` e `terraform.tfvars.example`. Arquivos locais como `.env`, `terraform.tfvars`, estados Terraform e caches Python sao ignorados pelo `.gitignore`.

## Encerramento dos recursos

Ao final da avaliacao, os recursos criados pelo Terraform podem ser removidos com:

```bash
cd assignment_2/task_2/grupo_3/final/terraform
terraform destroy
```

Se o bucket S3 contiver objetos e o Terraform bloquear a remocao, o bucket deve ser esvaziado antes:

```bash
BUCKET=$(terraform output -raw etl_bucket_name)
aws s3 rm "s3://$BUCKET" --recursive --region us-east-1
terraform destroy
```

O RDS usado como origem foi criado fora deste modulo Terraform. Portanto, se ele nao for mais necessario, deve ser removido separadamente no console do RDS.
