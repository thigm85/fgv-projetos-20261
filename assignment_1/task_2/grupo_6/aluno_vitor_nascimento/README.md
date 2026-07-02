## `Task 2`

### Estrutura do Projeto

```text
.
├── src/
│   ├── loader.py        # Carga inicial do RDS
│   ├── validate.py      # Validação da integridade do banco de origem
│   ├── glue_etl.py      # Script PySpark executado pelo AWS Glue
│   └── validate_etl.py  # Script de validação dos critérios (4.6)
├── terraform/
│   ├── main.tf          # Definição de recursos AWS
│   ├── terraform.tf     # Configuração de providers
│   └── terraform.tfvars # Variáveis sensíveis
└── requirements.txt     # Dependências Python
```

### Como Executar

#### 1. Preparação do Ambiente

Instale as dependências:
```bash
pip install -r requirements.txt
```

#### 2. Infraestrutura (Terraform)

Configure suas credenciais AWS e inicialize o Terraform:
```bash
cd terraform
terraform init
terraform plan
terraform apply
```
*Obs.: O Security Group está configurado para permitir acesso apenas ao seu IP atual automaticamente.*

#### 3. Carga do Sistema de Origem

Configure o arquivo `.env` com os dados de acesso gerados pelo Terraform e carregue os dados:
```bash
python src/loader.py
python src/validate.py  # Valida se o RDS foi populado corretamente
```

#### 4. Execução do ETL

Inicie o Job do Glue via Console da AWS ou CLI:
```bash
aws glue start-job-run --job-name rds-to-s3-star-schema
```

Aguarde o status do Job mudar para `SUCCEEDED`.

#### 5. Validação

Para garantir que os requisitos do item 4.6 foram atendidos, execute o script:
```bash
export S3_BUCKET_NAME="nome-do-seu-bucket"
python src/validate_etl.py
```
