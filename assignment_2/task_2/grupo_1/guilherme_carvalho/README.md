# Assignment 2 — Task 2: ETL Incremental, Partições e Agendamento

## Visão Geral

Este módulo evolui o pipeline ETL do Assignment 1 para modo **incremental**, com:

- **Extração filtrada por watermark**: somente pedidos novos (`orderDate > last_processed_order_date`) são processados a cada execução.
- **Particionamento Hive-style**: `fact_orders` é gravada no S3 com partições `order_year=YYYY/order_month=MM`.
- **Agendamento automático**: Amazon EventBridge dispara o Glue Job semanalmente via Terraform.

## Arquitetura

```
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

## Estrutura de Arquivos

```
assignment_2/task_2/grupo_1/guilherme_carvalho/
├── etl_job.py                # Script PySpark incremental (Glue Job)
├── main.tf                   # Provider e versões
├── variables.tf              # Variáveis de entrada
├── data.tf                   # Data sources (RDS, subnets, caller identity)
├── s3.tf                     # Bucket S3 para data lake
├── iam.tf                    # LabRole (data source)
├── vpc.tf                    # VPC Endpoint para S3
├── glue.tf                   # Glue Connection + Job
├── athena.tf                 # Glue Catalog (tabelas com partições) + Athena Workgroup
├── eventbridge.tf            # EventBridge Rule + Target para agendamento
├── outputs.tf                # Outputs do Terraform
├── terraform.tfvars.example  # Template de variáveis sensíveis
└── README.md                 # Este arquivo
```

## Pré-requisitos

1. **Assignment 1 Task 2** completo (RDS com `classicmodels` populado).
2. **Assignment 2 Task 1** completo (tabela `etl_watermark` criada e inicializada).
3. AWS CLI configurada com credenciais do lab.
4. Terraform >= 1.0 instalado.

## Variáveis de Conexão

Crie o arquivo `terraform.tfvars` (não commitado — protegido pelo `.gitignore`):

```hcl
rds_username = "SEU_USUARIO"
rds_password = "SUA_SENHA"
```

> ⚠️ **NUNCA** commite credenciais no repositório.

Variáveis opcionais (com defaults):

| Variável         | Default               | Descrição                        |
|------------------|-----------------------|----------------------------------|
| `aws_region`     | `us-east-1`           | Região AWS                       |
| `project_name`   | `classicmodels-etl`   | Prefixo para nomes de recursos   |
| `rds_instance_id`| `db-classicmodels`    | Identificador da instância RDS   |
| `rds_database`   | `classicmodels`       | Nome do banco de dados           |

## Como Executar

### 1. Provisionar infraestrutura

```bash
cd assignment_2/task_2/grupo_1/guilherme_carvalho/
terraform init
terraform plan
terraform apply
```

### 2. Fluxo completo de teste (executar pelo menos 2 vezes)

#### Execução 1 — Carga inicial

```bash
# 1. Simular novos pedidos (Task 1)
cd ../../task_1/grupo_1/guilherme_carvalho/
python incremental_source.py simulate --count 5 --seed 42

# 2. Executar o Glue Job (via console AWS ou CLI)
aws glue start-job-run --job-name classicmodels-etl-etl-job

# 3. Aguardar conclusão
aws glue get-job-run --job-name classicmodels-etl-etl-job --run-id <RUN_ID>
```

#### Execução 2 — Carga incremental

```bash
# 1. Simular mais pedidos
python incremental_source.py simulate --count 3 --seed 99

# 2. Executar novamente
aws glue start-job-run --job-name classicmodels-etl-etl-job
```

### 3. Disparar via EventBridge

O EventBridge está configurado para disparar automaticamente toda segunda-feira às 12:00 UTC. Para testar manualmente:

```bash
# Verificar regra
aws events describe-rule --name classicmodels-etl-etl-schedule

# O Job Run ID pode ser obtido no console do Glue ou via CLI
aws glue get-job-runs --job-name classicmodels-etl-etl-job --max-results 1
```

## Lógica do ETL Incremental

### Watermark

- O job lê `etl_watermark` no início para obter `last_processed_order_date`.
- Se `last_run_status = 'NEVER_RUN'` ou não há registro, faz **full load** (compatível com A1).
- Após sucesso, atualiza:
  - `last_processed_order_date = MAX(orderDate)` do batch processado
  - `last_run_at = UTC agora`
  - `last_run_status = 'SUCCEEDED'`
- Em caso de falha: `last_run_status = 'FAILED'` **sem avançar** a data.

### Extração

- **orders**: filtrados por `orderDate > last_processed_order_date`.
- **orderdetails**: filtrados por JOIN com os orders do delta.
- **Dimensões** (customers, products, offices, employees): reprocessadas completamente a cada run (Opção A — volume pequeno).

### Particionamento

`fact_orders` é gravada com partições Hive-style:

```
s3://<bucket>/analytics/fact_orders/order_year=YYYY/order_month=MM/part-….parquet
```

Colunas de partição:

| Coluna        | Tipo  | Origem        |
|---------------|-------|---------------|
| `order_year`  | `int` | Ano do pedido |
| `order_month` | `int` | Mês do pedido |

O modo de escrita usa `spark.sql.sources.partitionOverwriteMode = dynamic`, garantindo que somente partições tocadas pelo delta sejam sobrescritas.

### Star Schema

Mantém exatamente o contrato do A1:

- `fact_orders`: `order_id`, `customer_id`, `product_id`, `order_date_key`, `country_key`, `quantity_ordered`, `price_each`, `sales_amount`, `order_year`, `order_month`
- `dim_customers`: `customer_id`, `customer_name`, `contact_name`, `city`, `country`
- `dim_products`: `product_id`, `product_name`, `product_line`, `product_vendor`
- `dim_dates`: `date_key`, `full_date`, `year`, `quarter`, `month`, `day`
- `dim_countries`: `country_key`, `country`, `territory`

Regra de negócio: `sales_amount = quantity_ordered * price_each`.

## IAM — EventBridge

O EventBridge usa a **LabRole** (`arn:aws:iam::<account>:role/LabRole`) para invocar o Glue Job. Em laboratórios AWS Academy, a `LabRole` já possui a permissão `glue:StartJobRun` necessária.

Se estiver em um ambiente diferente, assegure-se de que a role atribuída ao EventBridge target tenha:

```json
{
  "Effect": "Allow",
  "Action": "glue:StartJobRun",
  "Resource": "arn:aws:glue:<region>:<account>:job/<job-name>"
}
```

## Validação

| #   | Verificação                                                                    |
| --- | ------------------------------------------------------------------------------ |
| 1   | Glue run `SUCCEEDED`                                                           |
| 2   | Novos objetos sob `fact_orders/order_year=…/order_month=…/`                    |
| 3   | `etl_watermark.last_processed_order_date` avançou                              |
| 4   | Athena: `SELECT COUNT(*) FROM fact_orders WHERE order_year = …` retorna linhas |
| 5   | Regras de `sales_amount` ainda válidas no delta                                |

## Evidências de Execução

_(Preencher após execução no ambiente AWS)_

### Execução 1
- **Job Run ID**: `<inserir>`
- **Pedidos simulados**: `<inserir>`
- **Linhas em fact_orders**: `<inserir>`

### Execução 2 (Incremental)
- **Job Run ID**: `<inserir>`
- **Watermark anterior**: `<inserir>`
- **Novos pedidos processados**: `<inserir>`
- **Linhas novas em fact_orders**: `<inserir>`

### Disparo via EventBridge
- **Job Run ID**: `<inserir>`
