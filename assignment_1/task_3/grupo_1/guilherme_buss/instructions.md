# Task 3 - Consultas Analíticas e Dashboard
## Guia Unificado de Arquitetura e Execução

Este documento consolida a arquitetura, a infraestrutura e o fluxo de execução para a implementação da Task 3.

---

### 1. Objetivo
Implementar consultas analíticas sobre o esquema estrela criado na Task 2 utilizando:
* **Amazon Athena**: Para executar consultas SQL sobre os dados em formato Parquet armazenados no Amazon S3.
* **AWS Data Wrangler (awswrangler)**: Para a integração nativa do ecossistema Python com o Amazon Athena.
* **Jupyter Notebook (Jupyter Lab)**: Para exploração interativa de dados e construção de um dashboard analítico.

O contexto de negócio é baseado no banco de dados `classicmodels`. Todas as consultas e o painel interativo utilizam exclusivamente o esquema estrela e os contratos de tabelas/colunas definidos anteriormente.

---

### 2. 🚀 Quick Start (Execução em 3 Passos)

Siga os passos abaixo para preparar a infraestrutura e executar o ambiente analítico:


```bash
# Passo 1: Provisionar a infraestrutura com o Terraform
cd grupo_1/guilherme_buss/
terraform init
terraform apply

# Passo 2: Validar a configuração gerada e o ambiente AWS
python validate.py

# Passo 3: Instalar as dependências e iniciar o Jupyter Lab
cd ../..
pip install -r requirements.txt
jupyter lab transformer.ipynb
```

---

### 3. Configuração Obrigatória

Antes de executar o comando `terraform apply`, certifique-se de configurar corretamente suas variáveis. Edite o arquivo `grupo_1/guilherme_buss/terraform.tfvars`:

```hcl
# --- Configuração Base ---
aws_region         = "us-east-1"
glue_database_name = "classicmodels"

```

O valor definido em `glue_database_name` deve corresponder exatamente ao nome do banco de dados criado no AWS Glue Data Catalog durante a Task 2. Se desejar usar um bucket S3 existente para os resultados do Athena, preencha a variável `athena_output_bucket`; caso contrário, deixe-a vazia `""` para que o Terraform crie um bucket exclusivo automaticamente.

---

### 4. Arquitetura do Fluxo de Dados

```
┌─────────────────────────────────────────────────────────────┐
│                  Task 2 Outputs (S3/Glue)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Star Schema Tables in Parquet Format               │  │
│  │  - fact_orders (S3 bucket de dados)                  │  │
│  │  - dim_customers, dim_products, dim_dates, etc.    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Terraform Resources                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. Reference Glue Database (from Task 2)          │  │
│  │  2. Create S3 Bucket for Athena Results            │  │
│  │  3. Generate config.py (notebook configuration)    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  Jupyter Notebook Execution                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  - Load config.py (Terraform outputs)              │  │
│  │  - Execute 3 Athena queries (awswrangler)         │  │
│  │  - Display results and visualizations             │  │
│  │  - Interactive dashboard with filters             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

```

---

### 5. Estrutura de Arquivos do Projeto

| Arquivo | Propósito |
| --- | --- |
| `main.tf` | Definição dos recursos principais: bucket S3 para resultados, data source do Glue e geração do `config.py`. |
| `variables.tf` | Declaração e tipagem das variáveis de entrada do Terraform. |
| `terraform.tfvars` | Definição dos valores específicos do ambiente (região, perfil, nome do banco Glue). |
| `validate.py` | Script de validação automatizada que testa a integridade do ecossistema local e remoto. |
| `transformer.ipynb` | Jupyter Notebook contendo a extração SQL via Athena, tratamento Pandas e o Dashboard interativo. |

---

### 6. Validação Automatizada (`validate.py`)

O script de validação realiza testes críticos antes de permitir a abertura do notebook. Ele assegura que:

1. O arquivo `config.py` foi gerado com sucesso pelo Terraform e contém todos os atributos obrigatórios (`GLUE_DATABASE`, `S3_OUTPUT`, `AWS_REGION`).
2. O banco de dados no AWS Glue Catalog existe e contém todas as tabelas requeridas (`fact_orders`, `dim_customers`, `dim_products`, `dim_dates`, `dim_countries`).
3. O bucket do S3 destinado ao armazenamento temporário de queries do Athena está acessível com as permissões corretas de leitura e escrita.

---

### 7. Estrutura do Jupyter Notebook

O arquivo `transformer.ipynb` está organizado estritamente de forma linear nas seguintes seções:

1. **Setup and Configuration**: Importação de bibliotecas (`awswrangler`, `pandas`, `seaborn`, `ipywidgets`) e carregamento dinâmico das variáveis geradas pelo Terraform contidas no `config.py`.
2. **Query 1 - Exploratory Query on dim_products**: Execução de uma consulta de amostragem (limite de 20 registros) para inspecionar e validar a conectividade direta com a tabela de produtos.
3. **Query 2 - Total Sales by Country**: Junção da tabela fato `fact_orders` com a dimensão `dim_countries` agrupando por país. Apresenta o top 10 em formato tabular e em um gráfico de barras estático.
4. **Query 3 - Detailed Sales Analysis**: Consolidação de uma base analítica ampla unindo a fato a três dimensões (`dim_products`, `dim_countries`, `dim_dates`). Os dados de data são convertidos para o tipo `datetime` nativo do Pandas para suportar filtros temporais dinâmicos.
5. **Interactive Dashboard**: Painel reativo construído com `ipywidgets` e gráficos atualizados em tempo real via `seaborn`.

#### Parâmetros de Filtro do Dashboard:

* Seleção de intervalo de datas (Data Inicial e Data Final baseado em `full_date`).
* Filtro por País (Dropdown contendo a opção agregadora "All").
* Filtro por Linha de Produto (Dropdown contendo a opção agregadora "All").
* Controle de Ranquamento Top N (Slider numérico parametrizado estritamente entre 1 e 10).

---

### 8. Critérios Mínimos de Conclusão e Sucesso

✓ **Infraestrutura**: Aplicação do plano do Terraform concluída sem erros de provisionamento.

✓ **Artefato de Configuração**: Arquivo `config.py` gerado dinamicamente com todas as strings mapeadas.

✓ **Verificação**: Script `validate.py` retornando sucesso em todas as etapas de checagem.

✓ **Mapeamento Analítico**: Execução bem-sucedida das três consultas contra o Amazon Athena.

✓ **Dashboard**: Filtros funcionando de maneira combinada, recalculando e renderizando o gráfico do Top N produtos corretamente conforme as seleções.

✓ **Consistência**: Uso exclusivo do modelo dimensional da Task 2, sem qualquer dependência ou consultas diretas ao banco relacional original (RDS) da Task 1.

---

### 9. Resolução de Problemas (Troubleshooting)

#### "Database not found" ou Erros de Tabelas Faltantes

Verifique se o nome do banco de dados no seu Glue Catalog confere com o que foi declarado no arquivo de variáveis:

```bash
aws glue get-databases --region us-east-1
aws glue get-tables --database-name <seu-database> --region us-east-1

```

#### Erros de Permissão ou "Access Denied" no Bucket S3

Certifique-se de que a sua sessão CLI ou perfil da AWS possui privilégios para ler e gravar dados no bucket de saída do Athena configurado:

```bash
aws sts get-caller-identity
aws s3 ls s3://seu-bucket-athena-output/

```

#### Componentes Visuais/Widgets Não Renderizam no Jupyter

Caso os seletores e botões do painel interativo não apareçam, execute a reinstalação e validação do gerenciador de extensões:

```bash
jupyter labextension list
jupyter labextension install @jupyter-widgets/jupyterlab-manager

```

---

### 10. Próximos Passos

1. **Particionamento**: Otimizar a performance física das consultas dividindo as tabelas Parquet no S3 por chaves temporais como Ano/Mês.
2. **BI**: Conectar o catálogo do AWS Glue ao Amazon QuickSight para publicação de painéis corporativos compartilháveis.
3. **Automação**: Agendar a atualização do pipeline e das views utilizando orquestradores como AWS Step Functions ou Apache Airflow.
"""

with open("data_pipeline_unificado.md", "w", encoding="utf-8") as f:
f.write(markdown_content)

print("Unified Markdown file created successfully.")

```
O seu arquivo unificado no formato Markdown está pronto!
[file-tag: code-generated-file-0-1779114980462460488]

O novo documento engloba as principais etapas do `QUICKSTART.md` direto no topo, seguindo pelas configurações de infraestrutura (Terraform), diagramas de arquitetura, estrutura detalhada do Jupyter Notebook e a seção de resolução de problemas do `data_pipeline.md`. Pode apagar com tranquilidade os outros dois arquivos e utilizar apenas esse novo documento para sua entrega.

```