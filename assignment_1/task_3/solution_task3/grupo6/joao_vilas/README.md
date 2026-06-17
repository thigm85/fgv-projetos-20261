# Task 3 - Consultas Athena + Dashboard Jupyter

Esta solucao estende e aprimora a Task 2 servindo o star schema atraves do Amazon Athena e um dashboard interativo em Jupyter. Toda a infraestrutura e declarativa (Terraform), credenciais ficam no AWS Secrets Manager e o notebook pode rodar tanto local quanto numa SageMaker Notebook Instance provisionada pelo proprio stack.

## Decisoes de arquitetura

A primeira decisao foi separar **Security Groups por servico**, em vez de jogar tudo num unico SG. O `rds_sg` so permite trafego 3306 vindo do IP administrativo `/32` configurado e do `glue_sg`; o `glue_sg` e self-referenciado, regra obrigatoria para o Spark do Glue conversar internamente entre seus workers. Isso aplica o principio do menor privilegio sem exigir nenhuma rede dedicada.

A segunda decisao foi tratar o **AWS Secrets Manager como fonte unica de verdade** para a senha do RDS. Um `random_password` do Terraform e gerado no proprio apply e gravado simultaneamente no segredo e nas connection properties da Glue Connection. Scripts locais e o notebook leem o segredo via `boto3` a partir do ambiente do usuario, que tem internet direta. O Glue Job nao precisa chamar Secrets Manager em tempo de execucao - usa a senha que ja foi embutida na Connection no apply -, o que elimina a dependencia de um VPC Interface Endpoint pra Secrets Manager e mantem a stack compativel com a default VPC do Learner Lab.

A terceira decisao foi declarar as **tabelas do Glue Data Catalog explicitamente no Terraform**, em vez de usar um Crawler. O schema vive em `main.tf` no local `local.fact_tables`, ficando travado e idempotente: o catalogo nao depende de fazer scan dos arquivos Parquet ja gravados, o que torna o apply mais rapido e o resultado mais previsivel.

Para o Athena, criamos um **workgroup dedicado com bucket de resultados separado** do bucket curated. O bucket de resultados aplica `SSE-S3` por padrao e tem regra de lifecycle expirando os outputs em 7 dias - resultados de query sao efemeros e nao precisam misturar com dados curados.

O **SageMaker fica fora da VPC** (`direct_internet_access = "Enabled"`, sem `subnet_id`/`security_group_id`). Athena, S3 e Secrets Manager sao endpoints AWS publicos consumidos via IAM; colocar o Notebook Instance em modo VPC adicionaria ENIs, NAT/endpoint extras e zero ganho. Um **lifecycle hook** do SageMaker sincroniza o `.ipynb` mais recente do S3 e injeta um `.env` com os outputs do Terraform antes do kernel iniciar, garantindo que `Run All` funcione direto.

Por fim, a stack **reusa a `LabRole` sem criar IAM**. O AWS Learner Lab proibe criar roles ou policies, entao usamos exclusivamente `data "aws_iam_role" "lab_role"` (leitura) e passamos esse ARN para o `role_arn` do Glue Job e do SageMaker Notebook. Nenhum recurso `aws_iam_role` ou `aws_iam_policy` e criado em parte alguma do Terraform.

## Compatibilidade com o AWS Learner Lab

A stack foi auditada para rodar dentro do AWS Academy / Learner Lab, onde a sessao do estudante tem permissoes amplas mas nao consegue criar nem alterar entidades IAM (roles, policies, users, etc.).

A restricao mais importante e a **proibicao de criar IAM**. O Terraform respeita isso com zero recursos `aws_iam_role`/`aws_iam_policy` - existe apenas o data source `data "aws_iam_role" "lab_role"`, que so faz `iam:GetRole`. O ARN obtido alimenta Glue Job e SageMaker via `role_arn = data.aws_iam_role.lab_role.arn`. O **`iam:PassRole`** funciona porque a `LabRole` do Learner Lab autoriza a si mesma como trust principal para os servicos `glue.amazonaws.com` e `sagemaker.amazonaws.com`, dispensando qualquer trust policy custom.

As **sessoes do Learner Lab expiram em ~4h**. Nada na stack depende de credencial de longa duracao: toda autenticacao para RDS, Athena, Glue e SageMaker vem da `LabRole` (ou do segredo no Secrets Manager). Quando a sessao expira, basta renovar pelo painel do lab que o ambiente continua funcional.

O **lab impoe quotas baixas** (tipicamente 1-2 RDS e 1-2 SageMaker Notebooks por sessao). A Task 3 cria **um unico RDS** e **um unico Notebook**; se a Task 2 ainda estiver viva, rode `terraform -chdir=terraform destroy` la antes para liberar slots. Caso a sua turma especifica do Academy tenha **SageMaker bloqueado**, basta passar `enable_sagemaker_notebook = false` no apply - Athena, Glue e o dashboard rodando localmente seguem funcionando.

A stack **nao cria VPC nova**: ela apenas le a default VPC via `data "aws_vpc" "default"` e reaproveita suas subnets e route tables. O **usuario que executa o `terraform apply`** no lab (`voclabs` ou `labuser`) ja tem permissoes wildcard em S3, Glue, Athena, SageMaker, Secrets Manager e RDS, alem de `iam:GetRole` e `iam:PassRole` em `LabRole` - exatamente o set que a stack precisa. **Logs do Glue em CloudWatch** funcionam porque a `LabRole` tem permissao de Logs (caminho ja validado na Task 2).

Em resumo, **nenhum** dos recursos da stack (RDS, SG, S3, Glue Connection, Glue Job, Glue Catalog, Athena, SageMaker, Secrets Manager) cria entidades IAM; o unico recurso "iam" e o data source de leitura `data.aws_iam_role.lab_role`. Se voce precisa rodar fora do Learner Lab, basta criar uma role equivalente manualmente e ajustar `var.lab_role_name` - para o lab, o default `"LabRole"` ja resolve.


## Fluxo de execucao

Todos os comandos assumem PowerShell rodando na raiz `joao_vilas/`. Para bash, troque `$env:` por `export` e `terraform -chdir=terraform` por `cd terraform && terraform`.

### 0. Pre-requisitos

AWS CLI com credenciais do Learner Lab ativas (`aws sts get-caller-identity` precisa devolver a conta do lab), Terraform `>= 1.5`, Python `>= 3.10` e o gerenciador [`uv`](https://docs.astral.sh/uv/).

### 1. Provisionar tudo

```powershell
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

O `apply` cria o RDS MySQL com SG proprio (3306 so a partir do seu IP `/32` e do Glue SG), o segredo no Secrets Manager com o JSON `{username, password, host, port, dbname}`, dois buckets S3 (`etl_bucket` e `athena_results`) mais o VPC Gateway Endpoint pro S3, toda a parte de Glue (Connection JDBC, Job Spark, Catalog database e cinco tabelas externas), o Athena workgroup com tres named queries persistidas e, se `enable_sagemaker_notebook = true`, o SageMaker Notebook Instance com lifecycle hook.

### 2. Popular o RDS

```powershell
uv sync
uv run python scripts/show_config.py        
uv run python scripts/load_data.py --dry-run
uv run python scripts/load_data.py
uv run python scripts/validate_data.py
```

Os scripts buscam a senha do RDS direto no Secrets Manager, nao precisam de `.env` com senha em texto claro.

### 3. Executar o Glue Job

```powershell
uv run python scripts/run_etl.py
```

O script dispara o Glue Job e bloqueia ate ele entrar em `SUCCEEDED` (ou falhar imprimindo a mensagem retornada pela API).

### 4. Validar os Parquets e o catalogo

```powershell
$BUCKET = terraform -chdir=terraform output -raw etl_bucket_name

aws s3 ls "s3://$BUCKET/curated/classicmodels/fact_orders/"    --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_customers/"  --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_products/"   --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_dates/"      --recursive
aws s3 ls "s3://$BUCKET/curated/classicmodels/dim_countries/"  --recursive

uv run python scripts/athena_smoke_test.py  
```

### 5. Abrir o dashboard

Localmente, basta rodar `uv run jupyter lab notebooks/classicmodels_dashboard.ipynb`. O notebook resolve a configuracao a partir dos outputs do Terraform automaticamente, sem nenhum passo manual.

Para rodar na AWS, confirme que `enable_sagemaker_notebook = true` (default) e aguarde a instancia ficar `InService`:

```powershell
$NbName = terraform -chdir=terraform output -raw sagemaker_notebook_name
aws sagemaker describe-notebook-instance --notebook-instance-name $NbName --query "NotebookInstanceStatus"
```

Quando o status virar `InService`, abra o JupyterLab pelo console (SageMaker -> Notebook instances -> Open JupyterLab) ou pela URL exibida em:

```powershell
terraform -chdir=terraform output -raw sagemaker_notebook_url
```

O lifecycle hook copia `classicmodels_dashboard.ipynb` para `SageMaker/task3/` e injeta o `.env` com `GLUE_DATABASE`, `ATHENA_WORKGROUP`, `ATHENA_OUTPUT_S3`, `DB_SECRET_ID` e `ETL_BUCKET` antes do kernel iniciar. Basta abrir o notebook e dar `Run All`.

### 6. Republicar o notebook (sem refazer apply)

```powershell
uv run python scripts/publish_notebook.py
```

Util quando voce so mexe no `.ipynb` e nao quer rodar `terraform apply` so para reenviar o arquivo.

## Modelo estrela servido pelo Athena

As cinco tabelas externas vivem no `aws_glue_catalog_database.classicmodels`. A **fato `fact_orders`** carrega as chaves `order_id`, `customer_id`, `product_id`, `order_date_key` e `country_key`, alem das metricas `quantity_ordered`, `price_each` e `sales_amount` (decimal calculado e validado pelo ETL contra `quantity_ordered * price_each`).

A dimensao **`dim_customers`** tras `customer_id`, `customer_name`, `contact_name`, `city` e `country`. A **`dim_products`** tras `product_id`, `product_name`, `product_line` e `product_vendor`. A **`dim_dates`** tras `date_key`, `full_date`, `year`, `quarter`, `month` e `day`. E a **`dim_countries`** mapeia `country_key` para `country` e `territory`.

Os schemas e os tipos sao **declarados explicitamente no Terraform** em `main.tf -> local.fact_tables`. E exatamente isso que distingue esta stack de uma baseada em Crawler: o catalogo nao depende de scan dos arquivos Parquet, ele e materializado no apply e o Athena ja encontra as tabelas no primeiro `SELECT`.

## Destruir o stack

```powershell
terraform -chdir=terraform plan -destroy -out=destroy.tfplan
terraform -chdir=terraform apply destroy.tfplan
```

Os buckets ja estao com `force_destroy = true`, mas confirme antes que nenhum Glue Job esta em `RUNNING` (`aws glue get-job-runs --job-name (terraform -chdir=terraform output -raw glue_job_name)`) para evitar timeout no destroy do Notebook Instance e da Connection.
