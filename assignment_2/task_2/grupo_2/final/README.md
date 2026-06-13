# Assignment 2 — Task 2: ETL incremental, partições e agendamento

Evolui o pipeline da [Task 1](../../../task_1/grupo_2/gustavo_tironi/README.md) (RDS +
`etl_watermark` + Lambda gateway) para um **Glue job incremental**: processa
só o delta de pedidos desde o watermark, grava `fact_orders` particionado por
`order_year`/`order_month` em `s3://<bucket>/analytics/...` e agenda execuções
automáticas via **EventBridge**. Detalhes do enunciado:
[incremental_etl.md](../../incremental_etl.md).
## Estrutura

```
gustavo_tironi/
├── terraform/        # IaC (RDS, S3, Glue, Athena, SageMaker, Lambda)
├── src/              # Scripts locais: load, init_watermark, validate
├── simulator/        # Gerador de pedidos novos (direto RDS ou via Lambda)
├── lambda/           # Handler order_gateway.py (deploy via Terraform)
├── tests/            # Bateria de testes end-to-end
├── glue/             # Job ETL (Task 2 do A1)
└── notebook/         # Dashboard (Task 3 do A1)
```

## Lambda gateway — o que faz

`lambda/order_gateway.py` recebe payload de pedido via `boto3.invoke()` e roda **5 verificações** antes de inserir no RDS:

1. `len(details) >= 1`
2. `customerNumber` existe em `customers`
3. todo `productCode` existe em `products`
4. `orderDate > etl_watermark.last_processed_order_date`
5. `quantityOrdered > 0` e `priceEach > 0`

Passou tudo → insere `orders` + `orderdetails` em transação. Qualquer falha → `{"status": "rejected", "errors": [...]}` e nada vai pro RDS.

Empacotada via **Lambda Layer** (`pymysql`) + ZIP só com o handler. Reusa `LabRole`, roda na mesma VPC do RDS.

## ETL incremental (Glue job)

`glue/glue_job_main.py` evolui o job full-reload do A1 para incremental. Um
único job, um único script — não existe versão "incremental" separada.

### EventBridge — o que é e como funciona

EventBridge é o agendador de eventos da AWS, equivalente a um `cron`
gerenciado. `terraform/eventbridge.tf` define:

- `aws_cloudwatch_event_rule.weekly_etl` — regra `cron(0 12 ? * MON *)`
  (semanal, segunda-feira ao meio-dia UTC).
- `aws_cloudwatch_event_target.glue_job` — aponta a regra para
  `aws_glue_job.etl`, chamando `glue:StartJobRun` automaticamente no horário
  agendado, sem intervenção manual.

**IAM / `LabRole`**: o target usa `local.glue_role_arn` (`LabRole`), já
definido em `main.tf` — não criamos role nova porque o AWS Academy não
permite. Testado via `terraform apply`: `LabRole` é aceita por
`events.amazonaws.com` como `role_arn` do target, sem erro de
IAM/AssumeRole.

### Lógica incremental — watermark e bootstrap

No início do job, lê `etl_watermark` (via `pymysql`, não Spark JDBC — é só um
valor escalar) para `pipeline_name = 'classicmodels_sales'`:

- **`last_run_status` em `NEVER_RUN`/`NULL` → bootstrap**: lê a tabela
  `orders` inteira (sem filtro). Como `s3://<bucket>/analytics/` é um
  prefixo novo (vazio), gravar tudo nele equivale a uma carga completa
  inicial — sem precisar de script de migração separado.
- **Caso contrário → incremental**: filtra
  `orders.orderDate > last_processed_order_date` via subquery JDBC.

### Extração filtrada das dimensões (Opção B)

Em vez de reler as tabelas-fonte inteiras a cada run (Opção A), aplicamos a
**Opção B**: em runs incrementais lemos via JDBC só as linhas-fonte
afetadas pelos pedidos novos. A partir do delta de `orders`:

- `orderdetails` → `WHERE orderNumber IN (...pedidos do delta...)`
- `customers` → `WHERE customerNumber IN (...clientes do delta...)`
- `products` → `WHERE productCode IN (...produtos do delta...)`

(`productlines`, `offices`, `employees` são tabelas de apoio minúsculas e sem
chave por pedido, então continuam lidas por completo.) No bootstrap tudo é
lido por inteiro. Helper único: `read_in(table, col, values)`.

### Estratégia de escrita: upsert por chave (idempotente)

| Tabela | Chave de merge | Modo |
|---|---|---|
| `fact_orders` | `(order_id, product_id)` | **append** particionado `order_year`/`order_month`, dedup contra partições tocadas (ver abaixo) |
| `dim_dates` | `date_key` | upsert (`upsert_dimension`) |
| `dim_customers` | `customer_id` | upsert (`upsert_dimension`) |
| `dim_products` | `product_id` | upsert (`upsert_dimension`) |
| `dim_countries` | `country` | upsert (`upsert_dimension`) |

As 4 dimensões usam o mesmo `upsert_dimension(df, name, key)`: lê o histórico
em `analytics/<dim>/`, remove (`left_anti`) as chaves presentes no delta e
regrava as versões novas por cima (`purge_s3_path` + escrita — o sink do Glue
só adiciona arquivos, por isso purgamos antes). No bootstrap não há histórico,
então grava a dimensão completa. É idempotente: reprocessar o mesmo delta
(ex.: retry após `FAILED`) dá o mesmo resultado, sem duplicar linhas.

> `dim_countries` agrega `first(territory)` por país. Como o mapeamento
> país→território é estável (mesmos escritórios), o upsert por `country` sobre
> o delta mantém o resultado consistente.

#### Merge incremental em `fact_orders`

`fact_orders` usa append (não dá para reescrever o prefixo inteiro a cada
run, perderíamos o histórico). Para evitar duplicar linhas em caso de retry
(job falha depois de escrever o parquet, mas antes de atualizar o watermark
→ próximo run reprocessa o mesmo delta), antes de escrever:

1. Identifica as partições `order_year=Y/order_month=M/` tocadas pelo delta.
2. Para as que já existem em S3, lê as chaves `(order_id, product_id)` já
   gravadas.
3. Remove do delta (`left_anti` join) as linhas cuja chave já existe.

Chave de negócio = `(order_id, product_id)`, conforme pedido no enunciado.

### Atualização do watermark

Só em sucesso lógico (sem exceção):
`last_processed_order_date = MAX(orderDate)` do delta processado,
`last_run_at = UTC now`, `last_run_status = 'SUCCEEDED'`. Em falha:
`last_run_status = 'FAILED'`, sem avançar a data — implementado com
try/except em torno de extração + transformação + escrita.

### Evidências de execução

Ver [`evidence/evidencia.md`](evidence/evidencia.md):
2 ciclos completos (`simulate_new_orders` → Glue incremental → validação
mínima) mais 1 disparo automático via EventBridge Scheduler. Cada ciclo
mostra o output do simulador, o Job Run ID do Glue e a checagem dos 5 itens
da "Validação técnica sugerida" — no Ciclo 2, com a saída completa do script
[`src/validate_etl_incremental.py`](src/validate_etl_incremental.py)
(rascunho da Task 3) e a conferência aritmética de que as linhas novas em
`fact_orders` batem com os pedidos simulados.

## Fluxo: apply → load → testes

```bash
cd terraform
AWS_PROFILE=projetos terraform apply         
cd ..

source .venv/bin/activate
AWS_PROFILE=projetos python src/load.py      
AWS_PROFILE=projetos bash tests/run_tests.sh 
```

### O que `run_tests.sh` cobre

| Passo | O quê |
|-------|-------|
| 1 | `validate_incremental_source` no estado inicial |
| 2 | Simulate **direto no RDS** (3 pedidos) |
| 3 | Simulate **via Lambda** (3 pedidos, gate ativo) |
| 4 | `test_lambda_rejections` — 5 cenários de dado ruim, todos rejeitados |
| 5 | `validate_incremental_source` final (deve passar) |

### Teste extra: validate pega dado quebrado

```bash
AWS_PROFILE=projetos bash tests/test_validate_catches_bad_data.sh
```

Injeta `orders` SEM `orderdetails` (bypassa Lambda), confirma que `validate_incremental_source` retorna **exit 1**, faz cleanup.

## Uso manual do simulator

```bash
# Direto no RDS (sem gate)
python simulator/simulate_new_orders.py --count 5 --seed 42

# Via Lambda gateway (com gate)
python simulator/simulate_new_orders.py --count 5 --seed 42 --via-lambda
```

Sem `--via-lambda` o script funciona 100% standalone — não depende da Lambda existir.

## Defesa em camadas

- **Lambda gateway** = barreira **na entrada** (rejeita antes do RDS)
- **`validate_incremental_source`** = barreira **pós** (detecta dado ruim que escapou por bypass)

## Dashboard (Task 3 do A1)

Continua funcionando inalterado — SageMaker Notebook Instance `classicmodels-dashboard`.

```bash
aws sagemaker start-notebook-instance --notebook-instance-name classicmodels-dashboard --profile projetos
aws sagemaker wait notebook-instance-in-service --notebook-instance-name classicmodels-dashboard --profile projetos

URL=$(aws sagemaker create-presigned-notebook-instance-url \
  --notebook-instance-name classicmodels-dashboard \
  --query AuthorizedUrl --output text --profile projetos)
NB_URL=$(echo "$URL" | sed 's|sagemaker\.aws?|sagemaker.aws/lab/tree/classicmodels/notebook/dashboard.ipynb?|')
open "$NB_URL"
```

Kernel = `conda_python3`. Auto-stop por 1h de idle (cron interno). Stop manual:

```bash
aws sagemaker stop-notebook-instance --notebook-instance-name classicmodels-dashboard --profile projetos
```

Detalhes completos: [terraform/DASHBOARD.md](terraform/DASHBOARD.md).

## Cleanup

```bash
cd terraform && AWS_PROFILE=projetos terraform destroy
```

Remove RDS, buckets, Glue, Lambda, layer, SGs, Secret, SageMaker. `force_destroy` no bucket de Athena.

## Configuração

`terraform/terraform.tfvars` (não commitado — ver `.gitignore`):

```hcl
senha_master   = "..."     # sem @, /, aspas
allowed_cidr   = ""        # vazio = auto-detect IP público
s3_bucket_name = "..."     # globalmente único
```

Após `apply`, `src/.env` é gerado com `SECRET_ARN`, `LAMBDA_ORDER_GATEWAY`, `GLUE_DATABASE`, etc.
