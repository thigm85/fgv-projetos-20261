# Assignment 2 — Task 1: Origem incremental + Lambda gateway

Pipeline que prepara o RDS `classicmodels` para cargas incrementais. Reusa toda a infra do A1 (RDS, Glue, S3, Athena, SageMaker) e adiciona uma camada de validação via **AWS Lambda** que atua como porta de entrada para pedidos simulados.

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

Empacotada via **Lambda Layer** (`mysql-connector-python`) + ZIP só com o handler. Reusa `LabRole`, roda na mesma VPC do RDS.

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
