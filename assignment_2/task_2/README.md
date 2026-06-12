# Assignment 2 — Task 2: ETL Incremental, Partições e Agendamento

## Visão Geral

Este diretório contém a evolução do pipeline ETL do Assignment 1 para **modo incremental**, com:

1. **ETL Incremental via Glue** — processa apenas pedidos novos (delta) desde o watermark
2. **Particionamento Hive-style** — `fact_orders` particionado por `order_year`/`order_month`
3. **Agendamento com EventBridge** — execução automática semanal via Terraform
4. **Glue Catalog** — tabelas registradas para consultas via Athena

## Estrutura de Diretórios

```
assignment_2/task_2/
├── glue_incremental_etl.py          # Script PySpark do Glue (ETL incremental)
├── terraform/
│   ├── main.tf                       # Recursos AWS (Glue job, EventBridge, Catalog)
│   ├── variables.tf                  # Definições de variáveis
│   ├── terraform.tfvars              # Valores reais (gitignored)
│   ├── terraform.tfvars.example      # Template sem senhas (commitado)
│   └── .gitignore                    # Protege state e tfvars sensíveis
├── evidence/                         # Prints/logs de execução
│   └── .gitkeep
├── README.md                         # Este arquivo
└── incremental_etl.md               # Especificação da tarefa
```

## Arquitetura

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

## Pré-requisitos

1. **Assignment 1 — Task 2** concluído: RDS provisionado, banco `classicmodels` populado, bucket S3 criado, Glue job original executado com sucesso
2. **Assignment 2 — Task 1** concluído: tabela `etl_watermark` inicializada, simulação de pedidos testada
3. **Terraform >= 1.0** instalado
4. **AWS CLI** configurado com credenciais válidas

## Configuração de Credenciais

### Segurança

> ⚠️ **NUNCA** commite senhas ou credenciais no repositório.

As credenciais JDBC do RDS estão armazenadas no **AWS Secrets Manager** (secret: `classic-models-etl/rds-credentials`), criado no Assignment 1. O Glue job lê esse secret automaticamente.

Para o Terraform, a senha do banco é passada via variável de ambiente:

**PowerShell:**
```powershell
$env:TF_VAR_db_master_password = "SuaSenhaAqui"
```

**Linux/macOS:**
```bash
export TF_VAR_db_master_password="SuaSenhaAqui"
```

### Configurar `terraform.tfvars`

1. Copie o template:
   ```bash
   cp terraform/terraform.tfvars.example terraform/terraform.tfvars
   ```
2. Preencha com os valores reais do seu ambiente A1:
   - `rds_endpoint`: endpoint do RDS (ex: `classic-models-db.xxxxx.us-east-1.rds.amazonaws.com:3306`)
   - `s3_bucket_name`: nome do bucket S3 do A1

   Esses valores podem ser obtidos dos outputs do Terraform do A1:
   ```bash
   cd ../../assignment_1/task_2/grupo_1/guilherme_buss
   terraform output
   ```

## Deploy (Terraform)

```bash
cd terraform/

# Inicializar
terraform init

# Validar configuração
terraform validate

# Visualizar plano
terraform plan

# Aplicar
terraform apply
```

Recursos criados:
| Recurso | Finalidade |
|---------|-----------|
| `aws_glue_job.incremental_etl` | Job Glue incremental com filtro por watermark |
| `aws_glue_catalog_database.analytics` | Database `classicmodels_analytics` para Athena |
| `aws_glue_catalog_table.fact_orders` | Tabela fato com partition keys `order_year`, `order_month` |
| `aws_glue_catalog_table.dim_*` | Tabelas de dimensão (customers, products, dates, countries) |
| `aws_cloudwatch_event_rule.glue_schedule` | Regra cron semanal (segunda, 12:00 UTC) |
| `aws_cloudwatch_event_target.glue_target` | Disparo do Glue job via EventBridge |
| `aws_cloudwatch_log_group` | Logs do Glue no CloudWatch |

## Lógica do ETL Incremental

### Fluxo do Script `glue_incremental_etl.py`

1. **Leitura do watermark** — conecta ao RDS via JDBC e lê `etl_watermark` para `pipeline_name = 'classicmodels_sales'`
2. **Extração filtrada** — extrai `orders` com `WHERE orderDate > last_processed_order_date` e `orderdetails` correspondentes
3. **Dimensões** — Opção A (reprocessamento completo a cada run)
4. **Transformação** — star schema com `fact_orders`, `dim_customers`, `dim_products`, `dim_dates`, `dim_countries`
5. **Merge incremental** — lê partições afetadas, remove duplicatas por (`order_id`, `product_id`), append do delta
6. **Particionamento** — grava `fact_orders` particionado por `order_year`/`order_month` (Hive-style)
7. **Watermark update** — atualiza `last_processed_order_date`, `last_run_at`, `last_run_status` somente em caso de sucesso

### Tratamento de Falhas

- Em caso de exceção, o watermark é atualizado com `last_run_status = 'FAILED'` **sem** avançar `last_processed_order_date`
- Isso garante que a próxima execução reprocessará os mesmos dados

### Primeira Execução Incremental (após A1)

- Se `last_run_status = 'NEVER_RUN'`, o script usa `'1900-01-01'` como watermark, processando **todo** o histórico
- Na primeira execução bem-sucedida, o watermark avança para `MAX(orderDate)` processado

### Colunas de `fact_orders`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `order_id` | int | Número do pedido |
| `customer_id` | int | FK para dim_customers |
| `product_id` | string | FK para dim_products |
| `order_date_key` | int | FK para dim_dates (formato yyyyMMdd) |
| `country_key` | int | FK para dim_countries |
| `quantity_ordered` | int | Quantidade pedida |
| `price_each` | decimal(10,2) | Preço unitário |
| `sales_amount` | decimal(12,2) | `quantity_ordered * price_each` |
| `order_year` | int | Partition key — ano do pedido |
| `order_month` | int | Partition key — mês do pedido (1–12) |

### Estrutura no S3

```
s3://<bucket>/output/fact_orders/order_year=2005/order_month=1/part-00000.snappy.parquet
s3://<bucket>/output/fact_orders/order_year=2005/order_month=2/part-00000.snappy.parquet
...
s3://<bucket>/output/dim_customers/part-00000.snappy.parquet
s3://<bucket>/output/dim_products/part-00000.snappy.parquet
s3://<bucket>/output/dim_dates/part-00000.snappy.parquet
s3://<bucket>/output/dim_countries/part-00000.snappy.parquet
```

## Execução e Evidência

### Fluxo de Teste Manual (mínimo 2 ciclos)

**Ciclo 1:**
```bash
# 1. Simular novos pedidos (A2T1)
cd ../task_1
python scripts/simulate_new_orders.py --count 5 --seed 42

# 2. Executar Glue job incremental (via console AWS ou CLI)
aws glue start-job-run --job-name classic-models-incremental-etl-job --region us-east-1

# 3. Acompanhar execução
aws glue get-job-run --job-name classic-models-incremental-etl-job --run-id <RUN_ID> --region us-east-1
```

**Ciclo 2:**
```bash
# 1. Simular mais pedidos
python scripts/simulate_new_orders.py --count 5 --seed 99

# 2. Executar novamente
aws glue start-job-run --job-name classic-models-incremental-etl-job --region us-east-1

# 3. Validar que apenas pedidos novos foram processados
# (Verificar nos logs do Glue: "Delta orders extracted: 5")
```

### Disparo via EventBridge

O EventBridge dispara automaticamente na programação configurada. Para forçar um disparo:

```bash
# Listar regras
aws events list-rules --region us-east-1

# O job será disparado automaticamente na próxima execução do cron
# Registre o Job Run ID do Glue após o disparo
```

### Validação via Athena

Após registrar as partições no Glue Catalog:

```sql
-- Reparar partições (necessário após primeira carga)
MSCK REPAIR TABLE classicmodels_analytics.fact_orders;

-- Consultar com filtro de partição
SELECT COUNT(*) AS total_rows
FROM classicmodels_analytics.fact_orders
WHERE order_year = 2005;

-- Validar sales_amount
SELECT order_id, product_id, quantity_ordered, price_each, sales_amount
FROM classicmodels_analytics.fact_orders
WHERE sales_amount != quantity_ordered * price_each;

-- Total por mês
SELECT order_year, order_month, COUNT(*) AS rows, SUM(sales_amount) AS total_sales
FROM classicmodels_analytics.fact_orders
GROUP BY order_year, order_month
ORDER BY order_year, order_month;
```

## EventBridge e Permissões IAM

### Role Utilizada

O EventBridge usa a role **`LabRole`** (pré-existente no ambiente de laboratório) para disparar o Glue job.

### Recursos Terraform

| Recurso | Finalidade |
|---------|-----------|
| `aws_cloudwatch_event_rule.glue_schedule` | Regra cron `cron(0 12 ? * MON *)` — semanal, segunda, 12:00 UTC |
| `aws_cloudwatch_event_target.glue_target` | Target apontando para o Glue job, usando `LabRole` como `role_arn` |

### Permissões da LabRole

A `LabRole` já possui todas as permissões necessárias no ambiente de laboratório:
- `glue:StartJobRun` — para iniciar o job Glue
- `glue:GetJobRun` — para monitorar execuções
- `s3:PutObject`, `s3:GetObject` — para leitura/escrita no bucket
- `secretsmanager:GetSecretValue` — para obter credenciais RDS
- `events:PutRule`, `events:PutTargets` — para EventBridge

## Checklist de Validação (pré-Task 3)

| # | Verificação | Status |
|---|-------------|--------|
| 1 | Glue run `SUCCEEDED` | ⬜ |
| 2 | Novos objetos sob `fact_orders/order_year=…/order_month=…/` | ⬜ |
| 3 | `etl_watermark.last_processed_order_date` avançou | ⬜ |
| 4 | Athena: `SELECT COUNT(*) FROM fact_orders WHERE order_year = …` retorna linhas | ⬜ |
| 5 | Regras de `sales_amount` válidas no delta | ⬜ |
| 6 | EventBridge disparou pelo menos 1 execução (Job Run ID registrado) | ⬜ |

## Troubleshooting

### Erro: "No watermark found"
**Causa:** `init_watermark.py` (A2T1) não foi executado.
**Solução:**
```bash
cd ../task_1
python scripts/init_watermark.py
```

### Erro: "No new orders to process"
**Causa:** Não há pedidos com `orderDate > last_processed_order_date`.
**Solução:** Execute `simulate_new_orders.py` para gerar dados novos.

### Erro: "Access Denied" no S3
**Causa:** LabRole sem permissão de escrita no bucket.
**Solução:** Verifique a policy da LabRole no IAM.

### Partições não aparecem no Athena
**Causa:** Partições não foram registradas no catálogo.
**Solução:**
```sql
MSCK REPAIR TABLE classicmodels_analytics.fact_orders;
```

## Referências

- [AWS Glue PySpark Documentation](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-python.html)
- [Amazon EventBridge User Guide](https://docs.aws.amazon.com/eventbridge/latest/userguide/)
- [Glue Catalog Partition Management](https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html)
- [Athena Partitioned Tables](https://docs.aws.amazon.com/athena/latest/ug/partitions.html)
- [Assignment 2 — Task 1 README](../task_1/README.md)
