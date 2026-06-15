# Assignment 2 — Task 2: ETL incremental, partições e agendamento

Evolução do pipeline do Assignment 1 para carga **incremental** governada por watermark,
com `fact_orders` **particionado** no S3 e **agendamento** automático via EventBridge.


## Decisões de arquitetura

- **Full load na 1ª execução, delta depois.** Se `etl_watermark.last_run_status = NEVER_RUN`,
  o job faz uma carga completa para semear o lake com o histórico do A1; nas execuções
  seguintes (`SUCCEEDED`) extrai apenas `orderDate > last_processed_order_date`.
- **Extração 100% via Glue JDBC** (nenhum CSV local). Em modo incremental, `orders` e
  `orderdetails` são filtrados por subconsulta JDBC; dimensões recarregadas por completo
  (Opção A do brief, adequada ao volume de laboratório).
- **`fact_orders` particionado** por `order_year`/`order_month` (Hive-style). O **merge**
  incremental lê apenas as partições afetadas, remove as chaves de negócio
  (`order_id`, `product_id`) presentes no delta e regrava com
  `partitionOverwriteMode=dynamic` — sem perder dados de meses anteriores.
- **Partition Projection** no Glue Catalog: o Athena enxerga as partições sem precisar de
  `MSCK REPAIR` nem crawler, bastando o layout Hive-style no S3.
- **Watermark atualizado só em sucesso.** `GREATEST` garante que a data nunca retrocede;
  em falha o job marca `FAILED` sem avançar a data processada.
- **Agendamento EventBridge → Lambda → Glue.** EventBridge Rules não têm target nativo de
  Glue; a Lambda intermediária chama `glue:StartJobRun`. Ver seção *Agendamento e IAM*.

## Contrato preservado do A1

`fact_orders` mantém `order_id, customer_id, product_id, order_date_key, country_key,
quantity_ordered, price_each, sales_amount` e acrescenta as partições `order_year`,
`order_month`. Regra mantida: `sales_amount = quantity_ordered * price_each`. As dimensões
(`dim_customers`, `dim_products`, `dim_dates`, `dim_countries`) seguem idênticas ao A1.

## Pré-requisitos

- Terraform ≥ 1.5, AWS CLI configurado para o Learner Lab, Python 3.10+ e `uv`.
- Credenciais do Learner Lab ativas (`aws sts get-caller-identity`).

## 1. Provisionar a infraestrutura

```powershell
aws sts get-caller-identity

$env:AWS_REGION = "us-east-1"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:TF_VAR_aws_region = "us-east-1"

$MyIp = (Invoke-RestMethod "https://checkip.amazonaws.com").Trim()
$env:TF_VAR_allowed_mysql_cidr = "$MyIp/32"

terraform -chdir=terraform init
terraform -chdir=terraform fmt -recursive
terraform -chdir=terraform validate
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan
```

A senha do RDS é gerada por `random_password` e guardada no **Secrets Manager** — nada de
senha em arquivo. Gere o `.env` para os scripts locais a partir dos outputs:

```powershell
$RdsHost = terraform -chdir=terraform output -raw rds_host
$Secret  = terraform -chdir=terraform output -raw db_secret_id
$Pass    = aws secretsmanager get-secret-value --secret-id $Secret --query SecretString --output text |
           ConvertFrom-Json | Select-Object -ExpandProperty password

@"
DB_HOST=$RdsHost
DB_PORT=3306
DB_USER=admin
DB_PASSWORD=$Pass
DB_NAME=classicmodels
PIPELINE_NAME=classicmodels_sales
AWS_REGION=us-east-1
"@ | Set-Content .env
```

## 2. Carregar dados e preparar o watermark

```powershell
uv sync
uv run python scripts/load_data.py            # carga histórica (classicmodels)
uv run python scripts/init_watermark.py       # cria/inicializa etl_watermark
uv run python scripts/validate_incremental_source.py
```

## 3. Ciclo incremental (executar pelo menos 2x — requisito 3.4.1)

```powershell
# 1ª execução: FULL load (semeia o lake com o histórico)
uv run python scripts/run_etl.py
uv run python scripts/validate_incremental_target.py --athena

# Simular novos pedidos e rodar de novo: apenas o delta é processado
uv run python scripts/simulate_new_orders.py --count 5 --seed 42
uv run python scripts/validate_incremental_source.py --expect-pending
uv run python scripts/run_etl.py
uv run python scripts/validate_incremental_target.py --athena
```

Na 2ª execução, confirme nos logs do Glue que `modo=INCREMENTAL` e que
`pedidos no escopo deste run` == nº de pedidos simulados, e que o watermark avançou.
Guarde os prints/logs em `evidence/`.

## 4. Disparar via EventBridge (requisito 3.4.3)

O cron padrão é semanal (`cron(0 12 ? * MON *)`). Para evidência imediata, dispare a regra
manualmente pela Lambda alvo e registre o **Job Run ID**:

```powershell
$LambdaName = terraform -chdir=terraform output -raw scheduler_lambda_name
aws lambda invoke --function-name $LambdaName response.json | Out-Null
Get-Content response.json        # contém o JobRunId retornado pelo StartJobRun

$JobName = terraform -chdir=terraform output -raw glue_job_name
aws glue get-job-runs --job-name $JobName --max-results 5 `
  --query "JobRuns[].{RunId:Id,State:JobRunState,TriggeredBy:TriggeredBy}" --output table
```

> A Lambda é exatamente o que o EventBridge chama no horário agendado; invocá-la
> diretamente exercita o mesmo caminho `EventBridge → Lambda → glue:StartJobRun`.

## Agendamento e IAM (Learner Lab)

| Recurso | Papel |
|---------|-------|
| `aws_cloudwatch_event_rule` | Regra cron (`var.schedule_expression`). |
| `aws_cloudwatch_event_target` | Aponta para a Lambda `start-glue-job`. |
| `aws_lambda_function` | Chama `glue:StartJobRun`; usa a **LabRole** como execution role. |
| `aws_lambda_permission` | Autoriza `events.amazonaws.com` a invocar a Lambda (policy de recurso). |

Esta stack **não cria IAM Roles** (restrição do Learner Lab): tanto o Glue Job quanto a
Lambda assumem a `LabRole` (`var.lab_role_name`), que já concede Glue/S3/Secrets Manager.
A permissão "EventBridge → Glue" é satisfeita pelo caminho EventBridge → Lambda → Glue.
Se a sua `LabRole` não permitir Lambda, alternativa equivalente é um
`aws_glue_trigger type = "SCHEDULED"` com o mesmo cron — documente a troca.

## Validação técnica (pré-Task 3)

| # | Verificação | Como |
|---|-------------|------|
| 1 | Glue run `SUCCEEDED` | `run_etl.py` / console Glue |
| 2 | Objetos sob `fact_orders/order_year=/order_month=` | `validate_incremental_target.py` |
| 3 | `etl_watermark.last_processed_order_date` avançou | query no RDS / validador |
| 4 | Athena retorna linhas com filtro de partição | `validate_incremental_target.py --athena` ou named query `sales-by-partition` |
| 5 | `sales_amount` válido no delta | checagem objetiva dentro do Glue Job |

## Destruir tudo

```powershell
terraform -chdir=terraform plan -destroy -out=destroy.tfplan
terraform -chdir=terraform apply destroy.tfplan
```
