## `Task 3`

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
├── dashboard.ipynb      # Notebook com consultas Athena e Dashboard Interativo
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
*Obs.: O Security Group está configurado para permitir acesso apenas ao seu IP atual automaticamente. O Terraform também criará o Glue Catalog Database e o Glue Crawler necessários para a Task 3.*

#### 3. Carga do Sistema de Origem

Configure o arquivo `.env` com os dados de acesso gerados pelo Terraform e carregue os dados:
```bash
python src/loader.py
python src/validate.py  # Valida se o RDS foi populado corretamente
```

#### 4. Execução do ETL (Task 2)

Inicie o Job do Glue via Console da AWS ou CLI:
```bash
aws glue start-job-run --job-name rds-to-s3-star-schema
```

Aguarde o status do Job mudar para `SUCCEEDED`.

#### 5. Validação do ETL (Task 2)

Para garantir que os requisitos do item 4.6 foram atendidos, execute o script:
```bash
export S3_BUCKET_NAME="nome-do-seu-bucket"
python src/validate_etl.py
```

---

## `Task 3 - Consultas e Dashboard`

#### 1. Catalogar as Tabelas no Glue Catalog
Após o término do Job do AWS Glue (Task 2), execute o Glue Crawler para descobrir os schemas e criar as tabelas no banco de dados do Glue Catalog:
```bash
aws glue start-crawler --name star-schema-crawler --region us-east-1
```
*Aguarde cerca de 1 a 2 minutos até que o Crawler retorne ao estado `READY` no console da AWS ou no CLI.*

#### 2. Abrir o Dashboard Interativo
Abra o Jupyter Lab ou VS Code na raiz do projeto:
```bash
jupyter lab
```
E abra o arquivo `dashboard.ipynb`. Execute todas as células para rodar as consultas SQL exploratórias diretamente no Athena (usando `awswrangler`) e interagir com o painel de vendas interativo criado com `ipywidgets` e `seaborn`.
