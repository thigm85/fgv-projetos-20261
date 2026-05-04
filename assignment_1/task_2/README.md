# Task 2: Pipeline de Dados ETL (AWS Glue & Terraform)

Este diretório contém a infraestrutura como código (IaC) e os scripts necessários para provisionar um pipeline de ETL na AWS. O pipeline extrai dados relacionais (MySQL) criados na **Task 1**, transforma-os em um esquema estrela (*Star Schema*) utilizando o **AWS Glue (PySpark)** e carrega os dados transformados no formato **Parquet** em um bucket **Amazon S3**.

---

## 📂 Estrutura de Arquivos

### 1. Terraform (`terraform/`)
Todos os recursos AWS são provisionados de forma automatizada e idempotente pelo Terraform. **Nenhuma configuração manual (como `.tfvars`) é necessária**, pois o Terraform se integra aos recursos da Task 1 de forma dinâmica (auto-detect).

- **`main.tf`**: Configuração do provider AWS.
- **`variables.tf`**: Definição das variáveis de ambiente com seus valores default.
- **`data.tf`**: Contém os *Data Sources* que detectam dinamicamente a VPC, Subnet, Security Group e o Endpoint do RDS criados na Task 1.
- **`iam.tf`**: Faz referência à `LabRole` (padrão de ambientes de laboratório AWS Academy) para contornar restrições de permissões.
- **`network.tf`**: Adiciona uma regra de auto-referência (*self-reference*) no Security Group do RDS para que os *workers* do Glue consigam se comunicar internamente.
- **`vpc_endpoint.tf`**: Cria um *S3 Gateway Endpoint* para permitir que o Glue (rodando dentro de uma VPC privada sem NAT Gateway) se comunique com a API do S3.
- **`s3.tf`**: Provisiona os dois buckets (um para armazenar os scripts do Glue e os arquivos temporários, e outro para salvar o output em Parquet) e faz o upload automático do script PySpark.
- **`glue_connection.tf`**: Configura a conexão JDBC segura para acessar o MySQL.
- **`glue_job.tf`**: Define o recurso `aws_glue_job`, configurando workers do tipo G.1X e os argumentos do PySpark.
- **`outputs.tf`**: Exibe informações e identificadores importantes no terminal ao fim da criação da infraestrutura.

### 2. Scripts ETL (`scripts/`)
- **`etl_classicmodels.py`**: Script PySpark que roda no AWS Glue. Ele extrai as 6 tabelas OLTP (`orders`, `orderdetails`, `customers`, `products`, `offices`, `employees`), aplica as transformações e joins necessários e as escreve no formato Parquet organizado nas seguintes tabelas de destino:
  - `fact_orders`
  - `dim_customers`
  - `dim_products`
  - `dim_dates`
  - `dim_countries`

### 3. Validação
- **`validate_etl.py`**: Script de auditoria local em Python usando `boto3` e `pandas`. Valida se os 4 critérios de aceitação foram cumpridos (Status `SUCCEEDED`, existência dos Parquets no S3, integridade referencial da *fact_orders* e corretude da coluna `sales_amount`).

---

## ⚙️ Como Executar

> **Pré-requisitos**: Certifique-se de que a **Task 1** já foi executada e a instância RDS (`classicmodels-db`) está com o status `available` na AWS. O banco já deve estar populado com as tabelas de origem. Além disso, você precisa do `aws-cli` configurado e do `terraform` instalados.

### Passo 1: Subir a Infraestrutura (Terraform)
Entre na pasta do Terraform e aplique o código. Ele usará as suas credenciais ativas da AWS para identificar o RDS automaticamente:

```bash
cd terraform
terraform init
terraform plan
terraform apply -auto-approve
```
*Aguarde a execução. Ao final, ele mostrará os outputs com os nomes dos recursos criados.*

### Passo 2: Executar o AWS Glue Job
Como a infraestrutura cria o job, mas não o executa automaticamente, você deve acionar o ETL via AWS CLI:

```bash
# Volte para a pasta da task_2
cd ..

# Inicie o Job e guarde o JobRunId gerado
aws glue start-job-run --job-name classicmodels-etl-job --region us-east-1
```

### Passo 3: Acompanhar a Execução
O Glue leva aproximadamente de 2 a 4 minutos para inicializar o cluster PySpark e rodar o job completo. Você pode monitorar o status:

```bash
aws glue get-job-runs \
  --job-name classicmodels-etl-job \
  --region us-east-1 \
  --query 'JobRuns[0].{Status:JobRunState,Start:StartedOn,Duration:ExecutionTime}' \
  --output table
```
*Repita o comando até que o `Status` fique como `SUCCEEDED`.*

### Passo 4: Validar os Resultados
Com o ETL finalizado com sucesso, instale as dependências de validação e rode o script Python:

```bash
# Instalar bibliotecas de dados e comunicação com a AWS
pip install boto3 pyarrow pandas

# Rodar a validação
python validate_etl.py
```
Se tudo funcionou corretamente, você verá uma mensagem no final dizendo **🎉 Pipeline ETL validado com sucesso!** acompanhada de 12 checks verdes (12 passed).

---

## 🧹 Limpeza (Destroy)
Para remover todos os recursos criados por esta Task (Buckets S3, Endpoints, Conexões e o Job do Glue) e não consumir os recursos do seu laboratório:

```bash
cd terraform
terraform destroy -auto-approve
```
