# Assignment 2 — Task 2: ETL incremental, partições e agendamento

Pipeline incremental **classicmodels_sales**: extrai delta do RDS via JDBC (filtro por `etl_watermark`), grava star schema em `s3://<bucket>/analytics/`, particiona `fact_orders` por `order_year` / `order_month`, atualiza watermark após sucesso e agenda execuções com **EventBridge → Glue** (Terraform).

A **Task 1** (`assignment_2/task_1/grupo_4/aluno_kaiky`) não é alterada por este diretório; use-a para `init_watermark`, `simulate_new_orders` e `validate_incremental_source`.

## Arquitetura

```text
RDS (classicmodels + etl_watermark)
  → Glue Job (JDBC, orderDate > watermark)
  → S3 analytics/ (fact_orders particionado + dim_*)
  → Glue Catalog / Athena
Glue trigger agendado (cron semanal, mesmo `glue_schedule_cron`)
```

## Pré-requisitos

- Task 1 concluída: RDS `classicmodels` populado e `etl_watermark` inicializado (`NEVER_RUN` com `last_processed_order_date = MAX(orders.orderDate)`).
- Terraform ≥ 1.5, AWS CLI, Python 3.10+ com `boto3` e `pyarrow` (validação local).
- Credenciais AWS (`aws sts get-caller-identity`).

## Setup único

Cada task mantém **suas próprias** credenciais locais (sem copiar arquivos entre pastas de tasks).

### 1. Variáveis locais (`.env`)

Na raiz desta task:

```powershell
cd assignment_2/task_2/grupo_4/aluno_kaiky
copy .env.example .env
```

Edite `.env` com `DB_PASSWORD`, `DB_USER`, `RDS_DB_INSTANCE_IDENTIFIER` e `AWS_REGION` do seu ambiente/lab. O arquivo `.env` não é commitado.

### 2. Terraform (`terraform.tfvars`)

Transfira os mesmos valores do `.env` para o Terraform (referência local, não script entre tasks):

```powershell
cd terraform
copy terraform.tfvars.example terraform.tfvars
```

Preencha em `terraform.tfvars`, no mínimo:


| Variável Terraform           | Origem no `.env`             |
| ---------------------------- | ---------------------------- |
| `aws_region`                 | `AWS_REGION`                 |
| `rds_db_instance_identifier` | `RDS_DB_INSTANCE_IDENTIFIER` |
| `db_name`                    | `DB_NAME`                    |
| `db_user`                    | `DB_USER`                    |
| `db_password`                | `DB_PASSWORD`                |


`terraform.tfvars` também está no `.gitignore` — nunca commite senhas.

### 3. Deploy da infraestrutura

```powershell
cd assignment_2/task_2/grupo_4/aluno_kaiky
python main.py deploy
```

Cria: bucket S3, script Glue no S3, Glue Connection/Job, catálogo (`fact_orders` com partition keys), **Glue trigger SCHEDULED** (cron padrão: segunda 12:00 UTC), regra SG **3306** RDS ← Glue.

## Execução direta (recomendado)


| Comando                  | O que faz                             |
| ------------------------ | ------------------------------------- |
| `python main.py deploy`  | `terraform init && apply`             |
| `python main.py run-etl` | Inicia Glue e aguarda `SUCCEEDED`     |
| `python main.py demo`    | Task 1 simulate → Glue → validação S3 |
| `python main.py full`    | deploy + demo                         |


Ciclo de evidência (enunciado 3.4) — **duas execuções**:

```powershell
# 1ª execução: baseline + primeiro delta
python main.py demo

# 2ª execução: novo simulate + incremental (preencha a seção Evidências abaixo)
python main.py demo
```

Scripts equivalentes:

```powershell
python scripts/run_incremental_cycle.py --count 5
python scripts/run_glue_job.py
python scripts/validate_etl_output.py
```

## Watermark e filtro incremental

- Pipeline: `classicmodels_sales` (tabela `etl_watermark`).
- Filtro: `orders.orderDate > last_processed_order_date` (tipo **DATE** no MySQL).
- Status `NEVER_RUN` na primeira carga incremental **não bloqueia** o filtro; usa a data já gravada pela Task 1.
- Em sucesso: `last_processed_order_date = MAX(orderDate)` do delta, `last_run_status = SUCCEEDED`.
- Em falha: `last_run_status = FAILED`, data **não** avança.
- Run sem pedidos novos: `SUCCEEDED` sem alterar a data.

## Saídas S3 e catálogo

Prefixo: `analytics/` (output `analytics_prefix`).

```text
s3://<bucket>/analytics/fact_orders/order_year=YYYY/order_month=MM/part-*.parquet
s3://<bucket>/analytics/dim_customers/
s3://<bucket>/analytics/dim_products/
s3://<bucket>/analytics/dim_dates/
s3://<bucket>/analytics/dim_countries/
```

Database Glue/Athena (default): `classicmodels_star_g4`.

```sql
SELECT COUNT(*) FROM fact_orders WHERE order_year = 2025 AND order_month = 6;
```

## Star schema (Assignment 1)

Mesmos nomes de tabelas/colunas; `sales_amount = quantity_ordered * price_each`. Dimensões: merge incremental (Opção B) apenas para entidades tocadas pelo delta. Fato: merge por `(order_id, product_id)` nas partições afetadas.

## Agendamento e IAM (3.1.2)

- O agendamento usa `**aws_glue_trigger**` (`type = SCHEDULED`) com `glue_schedule_cron`. EventBridge `PutTargets` **não aceita** ARN de Glue job diretamente (`ValidationException: Provided Arn is not in correct format`).
- **Role do job:** `glue_role_name` (default `**LabRole`**), mesma do Glue Job.
- Policy inline opcional (`eventbridge_attach_iam_policy = true`, default **false**) só se você customizar targets EventBridge; o trigger SCHEDULED não precisa dela.
- Policy manual (referência, se usar EventBridge Scheduler no futuro):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["glue:StartJobRun"],
    "Resource": ["arn:aws:glue:REGION:ACCOUNT:job/JOB_NAME", "arn:aws:glue:REGION:ACCOUNT:job/JOB_NAME/*"]
  }]
}
```

- A LabRole também precisa de trust para `events.amazonaws.com` se o console exigir (alguns labs já incluem na LabRole).

Registre um disparo na seção [Evidências (3.4)](#evidências-34) deste README.

Desabilitar agendamento:

```hcl
eventbridge_enabled = false
```

## Validação sugerida (pré-Task 3)


| #   | Verificação                                                       |
| --- | ----------------------------------------------------------------- |
| 1   | Glue run `SUCCEEDED`                                              |
| 2   | Objetos em `analytics/fact_orders/order_year=…/order_month=…/`    |
| 3   | `etl_watermark.last_processed_order_date` avançou após sucesso    |
| 4   | Athena `COUNT(*)` com filtro de partição retorna linhas           |
| 5   | `sales_amount` coerente (`python scripts/validate_etl_output.py`) |


## Evidências (3.4)

Preencha esta seção após rodar os testes na AWS (entrega / correção). Não é código executável.

**Script auxiliar** — imprime watermark, pending delta, S3, Glue runs etc. para copiar no README:

```bash
cd assignment_2/task_2/grupo_4/aluno_kaiky

# Depois do simulate, ANTES do 2º Glue run:
python scripts/print_evidence.py before

# Depois que o 2º Glue run terminar (SUCCEEDED):
python scripts/print_evidence.py after

# Referência §3.4.3 (trigger/cron + último JobRunId):
python scripts/print_evidence.py schedule
```

Requer: Terraform aplicado, Task 1 `.env` com `DB_PASSWORD`/`DB_HOST`, credenciais AWS e deps (`boto3`, `pyarrow`, `pymysql`, `python-dotenv` — mesmo venv da Task 1).

### Segunda execução incremental (3.4.2)

Após o **segundo** `python main.py demo` (com simulação de novos pedidos entre a 1ª e a 2ª execução).

**Watermark (RDS)**


| Campo                       | Antes do 2º Glue run | Depois do 2º Glue run |
| --------------------------- | -------------------- | --------------------- |
| `last_processed_order_date` | 2005-08-16           | 2005-08-23            |
| `last_run_at`               | 2026-06-12 00:37:49  | 2026-06-12 01:13:23   |
| `last_run_status`           | SUCCEEDED            | SUCCEEDED             |


```sql
SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status
FROM etl_watermark
WHERE pipeline_name = 'classicmodels_sales';
```

**Pedidos simulados (Task 1)** — cole a saída do `simulate_new_orders` desta rodada:

```
=== Simulation summary ===
Order IDs created     : [10481, 10482, 10483, 10484, 10485]
Order date range      : 2005-08-17 .. 2005-08-23
orderdetails rows     : 10

Line items (sales_amount = quantity * priceEach):
  order=10481 line=1 product=S50_4713 qty=39 price=63.92 sales_amount=2492.88
  order=10481 line=2 product=S12_3891 qty=14 price=95.54 sales_amount=1337.56
  order=10482 line=1 product=S24_2766 qty=39 price=88.53 sales_amount=3452.67
  order=10482 line=2 product=S24_1937 qty=3 price=31.53 sales_amount=94.59
  order=10483 line=1 product=S50_1392 qty=50 price=82.27 sales_amount=4113.50
  order=10483 line=2 product=S18_3136 qty=21 price=90.76 sales_amount=1905.96
  order=10484 line=1 product=S18_2248 qty=39 price=54.46 sales_amount=2123.94
  order=10484 line=2 product=S18_3782 qty=38 price=39.92 sales_amount=1516.96
  order=10485 line=1 product=S18_2325 qty=49 price=112.40 sales_amount=5507.60
  order=10485 line=2 product=S18_4933 qty=43 price=62.06 sales_amount=2668.58
```

**Coerência delta → fato**


| Métrica                                                    | Valor                                                               |
| ---------------------------------------------------------- | ------------------------------------------------------------------- |
| Pedidos com `orderDate > watermark` (antes do run)         | 5                                                                   |
| Linhas em `orderdetails` desses pedidos                    | 10                                                                  |
| Linhas novas/gravadas em `fact_orders` (partições tocadas) | 9                                                                   |
| Glue `JobRunId` (2ª execução)                              | jr_f6ece29716f543ad47998a0fea67c75258e43be64051305633b25076dfe4f7b9 |


### Disparo agendado (3.4.3)

Registre um disparo do **Glue trigger SCHEDULED** (cron) ou teste manual (`aws glue start-trigger --name …`).


| Item                                               | Valor                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------- |
| `eventbridge_rule_name` (output = nome do trigger) | **classicmodels-etl-g4-glue-schedule**                              |
| `glue_schedule_cron`                               | cron(0 12 ? MON )                                                   |
| Data/hora do disparo (UTC)                         | 2026-06-12 00:54:58.692000                                          |
| Glue `JobRunId`                                    | jr_7637b2f63050595dc92a91a91558db4cebb9024cf908527b7a998d5c69390272 |
| Estado final                                       | SUCCEEDED                                                           |


## Troubleshooting

### `AccessDenied: iam:CreateRole` / `iam:PutRolePolicy`

Use `glue_role_name = "LabRole"`. Para pular o agendamento: `eventbridge_enabled = false`.

### Glue não conecta ao RDS

O Terraform cria ingress **3306** do SG da Glue Connection para o SG do RDS. Confirme instância `rds_db_instance_identifier` igual à Task 1.

### State Terraform de outra conta

Arquive `terraform.tfstate` antigo e rode `terraform apply` na conta atual.

### `terraform apply` após editar o script

Sempre que alterar código em `glue_jobs/`, rode `terraform apply` (empacota zip + envia `etl_job.py` ao S3) e depois `python main.py run-etl`.

## Estrutura do diretório

```text
glue_jobs/              # Código PySpark do job (fora do Terraform)
  etl_job.py            # Entrypoint Glue
  constants.py          # Contratos do star schema / merge
  pipeline/             # extract | transform | load | validate
terraform/              # Infra (S3, Glue, Catalog, EventBridge, SG, VPC endpoint)
.env.example            # template de credenciais locais (copiar para .env)
scripts/                # run_glue_job, validate, print_evidence, incremental cycle
main.py                 # deploy | run-etl | demo | full
```

O Terraform referencia `../glue_jobs/` com `path.module` (nunca paths locais de máquina). O job usa `--extra-py-files` com `glue_modules.zip` (todos os módulos exceto `etl_job.py`).