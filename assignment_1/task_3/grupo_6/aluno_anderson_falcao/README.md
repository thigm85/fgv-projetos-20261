# Pipeline de Engenharia de Dados - Task 3 (Classicmodels)

Este repositório contém a implementação completa da **Task 3** do Assignment 1. O pipeline abrange desde o provisionamento de um banco de dados transacional MySQL no AWS RDS, passando por um processo de ETL usando o AWS Glue para gerar um *star schema* no formato Parquet no Amazon S3, e finalizando com consultas analíticas pelo Amazon Athena e um Dashboard no Jupyter Notebook.

## Estrutura do Projeto

* `terraform/`: Código de infraestrutura gerenciado pelo Terraform, que provisiona o RDS, os Buckets do S3, VPC Endpoints, o AWS Glue Job e o Glue Crawler/Athena Database.
* `scripts/`: Scripts em Python para as operações do banco de dados (carga dos dados, validação de integridade) e o próprio Job do Glue em PySpark.
* `dashboard/`: Jupyter Notebook para consultas no Amazon Athena e visualizações de BI interativas.

---

## 🚀 Como Executar

### Pré-requisitos
- Ambiente AWS (Academy LabRole disponível).
- AWS CLI e Terraform instalados e configurados com suas credenciais.
- Python e bibliotecas (`requirements.txt`).
- Arquivo de dados `.sql` localizado em `task_3/data/mysqlsampledatabase.sql` (na raiz do Assignment).

### Passo 1: Configurar Variáveis de Ambiente
Crie um arquivo chamado `.env` nesta pasta raiz (`task_3/grupo_6/aluno_anderson_falcao/.env`) com suas credenciais do banco:

```env
TF_VAR_db_username=usuario
TF_VAR_db_password=senha
```

### Passo 2: Provisionar Infraestrutura (Terraform)
1. Navegue até o diretório `terraform`:
   ```bash
   cd terraform
   ```
2. Inicialize e aplique o plano:
   ```bash
   terraform init
   terraform apply
   ```
3. Digite `yes` para confirmar. 
Isso irá criar sua instância RDS restrita ao seu IP atual, o Bucket S3 e configurar o Job do Glue.

### Passo 3: Carga e Validação de Dados
Volte para a pasta raiz deste módulo e execute os scripts (é necessário ter as libs do python instaladas como `mysql-connector-python` e `python-dotenv`). Os scripts buscarão os endpoints do RDS sozinhos usando o Terraform.

1. Carregar os dados iniciais (OLTP):
   ```bash
   python scripts/1_load_data.py
   ```
2. Validar a criação de tabelas e integridade relacional:
   ```bash
   python scripts/2_validate.py
   ```

### Passo 4: Executar o ETL (AWS Glue)
1. Abra o Console da AWS e navegue até o **AWS Glue**.
2. Na seção *ETL jobs*, selecione o Job chamado `classicmodels-etl-job`.
3. Clique em **Run**. Aguarde o status mudar para `SUCCEEDED` (pode demorar alguns minutos).
4. Em seguida, vá para *Crawlers* e rode o crawler `classicmodels-analytics-crawler` para popular o Glue Data Catalog com os esquemas gerados no S3.

### Passo 5: Analytics & Dashboard
1. Navegue até a pasta `dashboard/`:
   ```bash
   cd dashboard
   ```
2. Instale as dependências (já descritas no `requirements.txt`).

> **⚠️ IMPORTANTE: Uso do VSCode Recomendado**
> Recomendamos **fortemente** que você abra e execute o arquivo `analytics.ipynb` diretamente pelo **Visual Studio Code (VSCode)** utilizando a extensão nativa do Jupyter. 
> 
> O dashboard interativo utiliza a biblioteca **Plotly FigureWidget**, que possui suporte nativo e estável dentro do ambiente do VSCode. Caso tente abri-lo pelo navegador (via `jupyter lab`), o gráfico dinâmico não será renderizado corretamente a não ser que você instale extensões adicionais complexas de frontend do Jupyter.

3. Abra a pasta do projeto no VSCode.
4. Execute o arquivo `analytics.ipynb` pelo VSCode, rodando todas as células. Interaja com os botões e filtros para ver o dashboard interativo ser atualizado instantaneamente!
