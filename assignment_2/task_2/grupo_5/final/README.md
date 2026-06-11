# Assignment 2 — Task 2: ETL incremental, partições e agendamento

Solução do **Grupo 5** para `assignment_2/task_2/incremental_etl.md`.

Reutiliza o RDS do Assignment 1 (`classicmodels`), script incremental em PySpark e infraestrutura Terraform no Learner Lab.

## Estrutura

Árvore do que **vai no repositório** (commit). Arquivos locais/sensíveis ficam no `.gitignore`.

```text
grupo_5/final/
├── .gitignore
├── README.md
├── glue/
│   └── incremental_etl.py          # Job Glue (PySpark incremental)
├── terraform/
│   ├── main.tf                     # S3, Glue, SG, VPC endpoints, EventBridge, workflow
│   ├── variables.tf
│   ├── outputs.tf
│   ├── providers.tf
│   └── terraform.tfvars.example    # Modelo — copiar para terraform.tfvars
├── evidence/
│   └── run_log.md                  # Evidências dos 2+ ciclos incrementais
```

## Provisionamento

```bash
cp terraform.tfvars.example terraform.tfvars
# Edite db_host, vpc_id, subnet_id, db_security_group_id e senha
terraform init
terraform apply
```

Credenciais JDBC ficam em `terraform.tfvars` (sensível, listado no `.gitignore`).

### Recursos principais (após `terraform apply`)

| Recurso | Nome típico |
|---------|-------------|
| S3 | `grupo5-a2-task2-<suffix>` |
| Glue job | `grupo5-a2-task2-incremental-etl` |
| Glue database | `grupo5_a2_task2_analytics` |
| Glue connection | `grupo5-a2-task2-mysql-connection` |
| EventBridge rule | `grupo5-a2-task2-glue-schedule` |
| Glue workflow | `grupo5-a2-task2-etl-workflow` |

Outputs: `s3_bucket_name`, `glue_job_name`, `fact_orders_s3_path`, etc.

### IAM / EventBridge (Learner Lab)

- **Role:** `LabRole` (`glue_role_arn` no `terraform.tfvars`).
- **EventBridge → Glue Workflow:** o target usa `role_arn = LabRole`. No lab, essa role já possui permissões para invocar workflows/jobs Glue e escrever logs.
- Não foi criada role customizada (`iam:CreateRole` bloqueado no voclabs).

### Rede (VPC)

O job Glue usa conexão JDBC na VPC. O Terraform cria:

- **S3 Gateway Endpoint** — leitura/escrita do bucket e script do job.
- **Glue Interface Endpoint** — registro de partições no Data Catalog via API.

Sem esses endpoints, o job falha com erro de S3 ou timeout na API Glue.

## Lógica incremental (`glue/incremental_etl.py`)

| Tópico | Implementação |
|--------|----------------|
| Watermark | Lê `etl_watermark.last_processed_order_date` (`DATE`) para `classicmodels_sales`. Se `NULL`, usa `1900-01-01`. |
| Extração | JDBC com `orderDate > watermark`; dimensões lidas por tabela inteira. |
| Dimensões | overwrite completo de `dim_customers`, `dim_products`, `dim_countries`, `dates_dim`. |
| Fato | Merge por partição (`order_id`, `product_id`); chaves `order_year`, `order_month` derivadas de `orderDate`. |
| Partições S3 | `analytics/fact_orders/order_year=YYYY/order_month=MM/` |
| Watermark pós-run | Atualiza com `pymysql` somente em sucesso (`MAX(orderDate)` do delta). Em falha: `last_run_status = FAILED` sem avançar a data. |
| Bootstrap | Não há carga histórica completa — executar `simulate_new_orders` antes da 1ª execução no bucket vazio. |

`country_key` é `string` (MD5 do país), alinhado ao script incremental do grupo.

Timeout do job: **60 min** (2 workers `G.1X`, Glue 4.0).

## Fluxo de execução

```bash
# 1. Simular pedidos (Task 1)
python scripts/simulate_new_orders.py --count 5

# 2. Rodar Glue incremental
aws glue start-job-run --job-name grupo5-a2-task2-incremental-etl --region us-east-1

# 3. Validar watermark e integridade
python scripts/validate_incremental_source.py

# 4. Conferir S3
aws s3 ls s3://$(terraform output -raw s3_bucket_name)/analytics/ --recursive --region us-east-1
```

Repita o ciclo **pelo menos 2 vezes** (simulate → Glue → validar). Evidências em `evidence/run_log.md`.

Na 2ª execução, apenas pedidos com `orderDate` **estritamente maior** que o watermark anterior são extraídos; o volume em `fact_orders` deve ser coerente com o `--count` do simulate.

## Agendamento (EventBridge)

- **Cron (UTC):** `cron(0 12 ? * MON *)` — semanal, segunda 12:00 UTC.
- **Fluxo:** EventBridge → `grupo5-a2-task2-etl-workflow` → trigger EVENT → job `grupo5-a2-task2-incremental-etl`.

Teste manualmente pelo console (EventBridge → regra → **Send event**) ou aguarde o cron. Registre o Job Run ID em `evidence/run_log.md` quando testar.

## Athena (consulta de partições)

```sql
SELECT order_year, order_month, COUNT(*) AS n
FROM grupo5_a2_task2_analytics.fact_orders
GROUP BY order_year, order_month
ORDER BY order_year, order_month;
```

## Soluções de Problemas (lab)

| Problema | Ação |
|----------|------|
| `VPC S3 endpoint validation failed` | `terraform apply` (endpoint S3/Glue) |
| `File not present on S3` no merge | Script limpa prefixo antes de gravar; em caso extremo: `aws s3 rm s3://<bucket>/analytics/fact_orders/ --recursive` e reexecute |
| Glue lento (~5–15 min/run) | Normal (cold start + JDBC na VPC + dims completas) |
