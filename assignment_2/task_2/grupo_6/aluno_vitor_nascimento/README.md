## `(A2) Task 2`

### Estrutura do Projeto

```text
.
├── scripts/
│   ├── init_watermark.py              # Inicializa a tabela de watermark no RDS
│   ├── simulate_new_orders.py         # Simula a criação de novos pedidos no RDS
│   └── validate_incremental_source.py # Valida a origem incremental e o watermark
├── src/
│   ├── loader.py        # Carga inicial do RDS com dados históricos
│   ├── validate.py      # Validação da integridade do banco de origem
│   ├── glue_etl.py      # Script PySpark executado pelo AWS Glue (incremental, merge e particionamento)
│   └── validate_etl.py  # Script de validação dos critérios do ETL e S3
├── terraform/
│   ├── main.tf          # Definição de recursos AWS (RDS, S3, Glue Job/Workflow/Trigger, EventBridge)
│   ├── terraform.tf     # Configuração de providers
│   └── terraform.tfvars # Variáveis sensíveis (.gitignore)
├── dashboard.ipynb      # Notebook com consultas Athena e Dashboard Interativo
├── requirements.txt     # Dependências Python locais
└── README.md            # Este arquivo de documentação
```

---

### Como Executar e Testar

Siga as etapas abaixo para configurar, executar e validar o pipeline incremental completo.

#### Etapa 1: Preparação do Ambiente Local
Instale as dependências necessárias para rodar os scripts auxiliares:
```bash
pip install -r requirements.txt
```

#### Etapa 2: Provisionamento da Infraestrutura (Terraform)
1. Configure as credenciais da AWS em sua máquina.
2. Inicialize e implante os recursos na nuvem:
   ```bash
   cd terraform
   terraform init
   terraform apply
   ```
*Guarde os valores gerados nos outputs do Terraform: `rds_endpoint`, `s3_bucket`, `glue_job_name` e `glue_crawler_name`.*

#### Etapa 3: Configuração das Variáveis de Ambiente
Crie um arquivo `.env` na pasta `src/` (ou copie o `.env.example` e ajuste) com as credenciais do seu banco de dados e datalake providos pelo Terraform:
```env
DB_HOST=<rds_endpoint_do_terraform>
DB_USER=<seu_usuario_rds>
DB_PASS=<sua_senha_rds>
DB_NAME=classicmodels
S3_BUCKET_NAME=<s3_bucket_do_terraform>
```

#### Etapa 4: Carga Histórica da Origem
Popule a base de dados MySQL RDS com a carga inicial e valide o baseline do banco:
```bash
cd ../ # Volte para a raiz do projeto (task_2)
python src/loader.py
python src/validate.py
```

#### Etapa 5: Inicialização do Controle de Watermark
Execute o script para criar a tabela `etl_watermark` no RDS. Ele definirá o watermark inicial (`last_processed_order_date`) com base na data máxima dos dados históricos atuais:
```bash
python scripts/init_watermark.py
```

#### Etapa 6: Primeira Execução do Glue (Baseline do S3)
Inicie o Glue Workflow para rodar o Job pela primeira vez. Isso irá estruturar a tabela `fact_orders` no S3 em formato **particionado** e atualizar o status do watermark para `SUCCEEDED`:
```bash
aws glue start-workflow-run --name rds-to-s3-star-schema-workflow --region us-east-1
```
*Aguarde a execução do Job finalizar com status `SUCCEEDED` no console do AWS Glue (pode demorar).*

#### Etapa 7: Simulação de Novos Pedidos (Carga Incremental)
Insira novos pedidos fictícios com datas estritamente posteriores ao watermark histórico e execute o script de validação de origem:
```bash
# Simula 10 novos pedidos na origem RDS
python scripts/simulate_new_orders.py --count 10 --seed 42

# Valida se os novos pedidos foram detectados em relação ao watermark
python scripts/validate_incremental_source.py
```

#### Etapa 8: Segunda Execução do Glue (Processamento do Delta)
Inicie o Glue Workflow novamente. Desta vez, o Job processará **apenas os 10 novos pedidos**, unindo-os ao histórico no S3 de forma incremental sem duplicar registros, e avançará a data do watermark no RDS:
```bash
aws glue start-workflow-run --name rds-to-s3-star-schema-workflow --region us-east-1
```
*Aguarde o status final do Job atingir `SUCCEEDED`.*

#### Etapa 9: Catalogação de Partições e Validação Final do ETL
Rode o Glue Crawler para descobrir as novas partições criadas no S3 e execute o validador para garantir a integridade dos dados e cálculos:
```bash
# Inicia o Crawler para ler as partições do S3 e alimentar o Glue Catalog/Athena
aws glue start-crawler --name star-schema-crawler --region us-east-1

# (Aguarde 1 a 2 minutos até que o Crawler retorne ao estado READY)

# Executa as regras de sanidade sobre os dados do S3 (verifica duplicados, sales_amount, chaves nulas)
python src/validate_etl.py
```

#### Etapa 10: Consulta dos Resultados e Dashboard Interativo
Abra o Jupyter Lab ou seu editor na raiz do projeto:
```bash
jupyter lab
```
Abra o notebook `dashboard.ipynb` e execute todas as células para interagir com o painel de métricas e realizar consultas ad-hoc no Athena.

---

### Detalhes Técnicos da Task 2

#### 1. Tipo de Dados do Watermark
A coluna `last_processed_order_date` na tabela `etl_watermark` é do tipo **`DATE`** do MySQL. A comparação no filtro do Spark SQL é feita convertendo essa data para string e comparando diretamente com a coluna `orderDate` da tabela `orders` (`orderDate > last_processed_order_date`).

#### 2. Agendamento e Permissões IAM (EventBridge → AWS Glue)
- **Fluxo de Agendamento**: Como a API de regras do Amazon EventBridge (`aws_cloudwatch_event_target`) não suporta nativamente o acionamento direto de um Glue Job através de seu ARN de recurso (gerando erro de validação de formato), implementamos um **AWS Glue Workflow** (`rds-to-s3-star-schema-workflow`) e um **AWS Glue Trigger** de início do tipo `EVENT`. O EventBridge aciona o Workflow, que por sua vez dispara a execução do Glue Job automaticamente.
- **Role do EventBridge**: O AWS EventBridge utiliza a role **`LabRole`** (especificada como `role_arn` no target da regra do CloudWatch Event) para iniciar o Workflow.
- **Permissões Associadas**: No ambiente de laboratório (AWS Academy), a `LabRole` já possui as permissões necessárias para interagir com o Glue (`glue:StartWorkflowRun` / `glue:StartJobRun`) e a relação de confiança (trust policy) para permitir a execução via `events.amazonaws.com`.

#### 3. Evidências de Execução da Task 2
As evidências completas da execução do pipeline incremental, validação do watermark, coerência na contagem de registros e agendamento via EventBridge/Workflow estão documentadas na pasta dedicada [evidence/](file:///home/vitor/FGV/Projetos/fgv-projetos-20261/assignment_2/task_2/grupo_6/aluno_vitor_nascimento/evidence/README.md).
