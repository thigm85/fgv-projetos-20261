# Um Exemplo do Ciclo de Vida de Engenharia de Dados — consultas e visualização

Este trabalho é uma adaptação de um exercício presente no curso [Introduction to Data Engineering](https://www.coursera.org/learn/intro-to-data-engineering), que integra o DeepLearning.AI Data Engineering Professional Certificate.

Neste laboratório, você irá configurar e executar um exemplo de pipeline de dados que demonstra todas as etapas do ciclo de vida da engenharia de dados. Seu sistema de origem será um banco de dados relacional instanciado como um banco MySQL no Amazon RDS (Relational Database Service). Primeiro, você irá explorar o banco de dados de origem utilizando um conjunto de dados de exemplo, depois usará o AWS Glue para extrair, transformar e carregar (ETL) os dados no seu pipeline, armazenando-os no serviço de armazenamento de objetos da AWS, o Amazon S3. Por fim, você irá consultar os dados armazenados utilizando o Amazon Athena para montar um dashboard de visualização de dados no Jupyter Lab. Para definir e configurar os componentes deste exemplo de pipeline de dados, será utilizado o Terraform como serviço de Infraestrutura como Código (IaC).

## 1 - Introdução

Suponha que você trabalha como Engenheiro de Dados em uma loja de carros clássicos e outros meios de transporte. Essa loja armazena seus históricos de compras e as informações de seus clientes em um banco de dados relacional que contém as seguintes tabelas: customers, products, productlines, orders, orderdetails, payments, employees, offices. Neste laboratório, você usará um exemplo desse banco de dados: [MySQL Sample Database](https://www.mysqltutorial.org/mysql-sample-database.aspx)

O analista de dados do time de marketing está interessado em analisar os históricos de compras para entender, por exemplo, qual linha de produtos é mais bem-sucedida e como as vendas estão distribuídas entre os diferentes países. Embora o analista de dados possa consultar diretamente os dados no banco relacional, pode ser necessário escrever consultas complexas que podem levar muito tempo para recuperar as informações desejadas. Realizar consultas analíticas em bancos de dados de produção geralmente não é uma boa ideia, pois pode impactar o desempenho desses bancos. Seu trabalho como Engenheiro de Dados é construir um pipeline de dados que transforme os dados em uma forma mais fácil de entender e mais rápida de consultar, servindo-os para o analista de dados focar apenas na análise.

Neste laboratório, você irá explorar um exemplo de ponta a ponta que mostra a implementação das etapas do ciclo de vida de engenharia de dados na AWS.

Vamos começar explorando o sistema de origem!

## 2 - Task 1: Explorando o Sistema de Origem

O primeiro desafio é criar e popular o sistema de origem do pipeline: um banco de dados MySQL provisionado no Amazon RDS, contendo as tabelas necessárias para o laboratório.

Recomendamos organizar esse processo com scripts Python para automatizar e tornar as etapas reprodutíveis, facilitando a execução a partir do seu computador local:

- **Provisionamento do RDS:** Script para criar sua instância de banco MySQL no Amazon RDS.
- **Load de Dados:** Script para criar o banco `classicmodels` e carregar os dados de exemplo do arquivo SQL.
- **Validação:** Script para conferir se todas as tabelas foram criadas e populadas corretamente.

O uso desses scripts ajuda a evitar erros manuais, melhora a rastreabilidade e possibilita que todo o fluxo seja executado diretamente do seu ambiente local, seja via terminal, scripts ou ferramentas gráficas, conforme sua preferência.

**Fluxo sugerido:**

1. Execute o script de provisionamento para criar sua instância MySQL no RDS.
2. Use o script de carga para criar e popular o banco `classicmodels` com os dados de exemplo.
3. Execute o script de validação para garantir que as tabelas e dados estão corretos.

Você deve ser capaz de executar todas as etapas acima a partir do seu computador local, registrando e utilizando as informações essenciais de acesso ao banco (nome, usuário administrador, senha e endpoint). Nos próximos passos, esse banco será utilizado como sistema de origem para o pipeline de dados.

## 3 - Task 2: Pipeline de dados - ETL

### 3.1 - Arquitetura do Pipeline de Dados

A arquitetura proposta extrai os dados da instância do banco de dados MySQL no RDS e usa o AWS Glue para transformar e armazenar os dados em um bucket S3 (serviço de armazenamento de objetos).

Segue uma breve descrição dos componentes:

- **Banco de Dados de Origem:** Você já interagiu com o banco de dados de origem na seção anterior. Trata-se de um banco de dados relacional que armazena tabelas estruturadas e normalizadas. Mais especificamente, ele representa um sistema de Processamento de Transações Online (OLTP) que armazena dados transacionais, onde uma transação neste trabalho representa um pedido de venda realizado por um cliente.
- **Extraction, Transformation and Load (ETL):** O segundo componente é o [AWS Glue](https://aws.amazon.com/pt/glue/).
  - **Extração:** Esta etapa envolve extrair dados do banco OLTP. Um Job do AWS Glue é utilizado para conectar-se ao banco RDS e recuperar os dados.
  - **Transformação:** Após a extração dos dados, o Glue realiza a transformação dos mesmos. Você pode especificar, no Glue, qual tipo de transformação deseja realizar sobre os dados extraídos. Neste laboratório, a transformação consiste em modelar os dados em um esquema estrela ("star schema"), diferente do banco de origem. O esquema estrela facilita a leitura e o uso dos dados pelo analista, tornando a escrita de consultas muito mais simples para suas análises. Converter os dados para um esquema estrela pode envolver tarefas como desnormalização, agregações e eventuais limpezas ou enriquecimento dos dados.
  - **Load:** Esta etapa envolve armazenar os dados transformados em um sistema de armazenamento. O sistema escolhido neste trabalho é a solução de armazenamento de objetos da AWS: [Amazon S3](https://aws.amazon.com/pt/s3/). O S3 é uma solução escalável e com ótimo custo-benefício, podendo fazer parte de data lakes e data warehouses. Os dados transformados são armazenados em um formato chamado Parquet, que é otimizado para uso analítico.

### 3.2 - Extração, Transformação e Load

Agora que você já entende os diferentes componentes da sua arquitetura de dados, você irá configurar e executar um pipeline ETL completo, criando os artefatos mínimos por conta própria. Nesta tarefa, toda a provisão e configuração devem ser declaradas e executadas via Terraform. O objetivo é sair de um modelo transacional (OLTP) e produzir dados analíticos em formato Parquet no S3.

**3.2.1.** Crie os artefatos mínimos de infraestrutura necessários para executar ETL com AWS Glue:

- Um bucket S3 para armazenar os dados transformados.
- Uma IAM Role para o Glue com permissões de leitura no RDS (via conexão), escrita no S3 e logs no CloudWatch.
- Uma conexão do Glue com sua instância MySQL no RDS.
- Um Job do Glue para executar o processo de extração, transformação e carga.

Nesta tarefa, crie esses recursos exclusivamente via Terraform.

**3.2.2.** Configure o Job do Glue para **extrair** dados do banco `classicmodels`, priorizando as tabelas necessárias para o modelo analítico. No mínimo, inclua informações de pedidos, clientes, produtos e localidade para suportar análises de vendas.

**3.2.3.** Implemente no Job do Glue a **transformação** para esquema estrela. O resultado esperado é, no mínimo, este conjunto de tabelas:

- **fact_orders** (tabela fato):
  - chaves para dimensões: `order_id`, `customer_id`, `product_id`, `order_date_key`, `country_key`
  - métricas de negócio: `quantity_ordered`, `price_each`, `sales_amount`
- **dim_customers**:
  - `customer_id`, `customer_name`, `contact_name`, `city`, `country`
- **dim_products**:
  - `product_id`, `product_name`, `product_line`, `product_vendor`
- **dim_dates**:
  - `date_key`, `full_date`, `year`, `quarter`, `month`, `day`
- **dim_countries** (ou dimensão equivalente de localização):
  - `country_key`, `country`, `territory`

Para padronização da avaliação desta tarefa, mantenha exatamente os nomes de tabelas e colunas especificados acima.

**3.2.4.** Execute a etapa de **load** gravando as tabelas transformadas no S3 em formato Parquet, separadas por entidade (por exemplo, uma pasta por tabela de saída).

**3.2.5.** Execute o fluxo definido no Terraform para provisionar e atualizar os recursos do pipeline e, em seguida, acompanhe a execução do Job do Glue até o status `SUCCEEDED`.

**3.2.6.** Valide o resultado do ETL com os seguintes critérios mínimos:

1. O job finaliza com status `SUCCEEDED`.
2. As saídas Parquet de `fact_orders` e das dimensões existem no bucket S3.
3. A tabela fato contém registros e referencia chaves válidas das dimensões.
4. O campo `sales_amount` (ou métrica equivalente) está consistente com a regra `quantity_ordered * price_each`.

Após essa validação, considere o pipeline ETL concluído para esta fase do trabalho.

## 4 - Task 3: Consultas analíticas e dashboard

Nesta etapa você **serve** os dados já transformados na Task 2: consultas no **Amazon Athena** sobre as tabelas do catálogo Glue (dados em Parquet no S3) e um **dashboard interativo** no Jupyter (por exemplo, Jupyter Lab), usando Python. O contexto de negócio continua sendo o do **Task 1** (banco `classicmodels` no RDS como origem transacional); porém **todas** as consultas e o dashboard desta tarefa devem usar **exclusivamente** o **esquema estrela e os nomes de tabelas e colunas** definidos na Task 2.

### 4.1 - Configuração

- Defina uma variável Python com o **nome do database** no Glue/Athena apontando para as tabelas que você materializou na Task 2 (substitua pelo valor real do seu ambiente, inclusive se o Terraform usar um nome fixo).

```python
GLUE_DATABASE = "substitua_pelo_nome_do_seu_database_no_glue_athena"
```

- Utilize o [AWS Data Wrangler](https://aws-sdk-pandas.readthedocs.io/) (`awswrangler`), `pandas`, `seaborn` e `ipywidgets` (e `IPython.display` se precisar de `display`), com credenciais AWS válidas na sessão onde o notebook roda.

### 4.2 - Consulta exploratória em dimensão

Execute uma consulta simples em `dim_products` para inspecionar o catálogo de produtos no modelo analítico, por exemplo:

```sql
SELECT
    product_id,
    product_name,
    product_line,
    product_vendor
FROM dim_products
LIMIT 20
```

Carregue o resultado com `wr.athena.read_sql_query(..., database=GLUE_DATABASE)` e exiba as primeiras linhas.

### 4.3 - Vendas totais por país

Calcule o total de vendas por país juntando a fato à dimensão de país pela chave `country_key`, agregando `sales_amount`:

```sql
SELECT
    dim_countries.country,
    SUM(fact_orders.sales_amount) AS total_sales
FROM fact_orders
JOIN dim_countries ON fact_orders.country_key = dim_countries.country_key
GROUP BY dim_countries.country
ORDER BY total_sales DESC
LIMIT 10
```

### 4.4 - Detalhamento por data, linha de produto, produto e país

Combine `fact_orders` com `dim_products`, `dim_countries` e `dim_dates` para obter uma base analítica no grão (data do pedido, linha de produto, nome do produto, país) com `SUM(sales_amount)`:

```sql
SELECT
    dim_dates.full_date,
    dim_products.product_line,
    dim_products.product_name,
    dim_countries.country,
    SUM(fact_orders.sales_amount) AS total_sales
FROM fact_orders
JOIN dim_products ON fact_orders.product_id = dim_products.product_id
JOIN dim_countries ON fact_orders.country_key = dim_countries.country_key
JOIN dim_dates ON fact_orders.order_date_key = dim_dates.date_key
GROUP BY
    dim_dates.full_date,
    dim_products.product_line,
    dim_products.product_name,
    dim_countries.country
```

Armazene o resultado em um DataFrame; converta a coluna de data para tipo datetime do `pandas` quando for filtrar por intervalo de datas no dashboard.

### 4.5 - Dashboard interativo

Construa um painel interativo inspirado no fluxo “explorar → agregar → filtrar → ranquear”, com:

- Seleção de **intervalo de datas** (com base em `full_date` obtida via `dim_dates` na consulta da subseção 4.4).
- Filtros por **país** e por **linha de produto** (`product_line`), com opção “todos” equivalente ao comportamento agregador que você julgar adequado.
- Controle de **Top N** (por exemplo, slider entre 1 e 10).
- Gráfico de barras (`seaborn`) com vendas totais no eixo horizontal e **nome do produto** no vertical, mostrando os **Top N** produtos após aplicar os filtros.

A lógica deve espelhar o padrão de um dashboard por widgets (filtros reexecutando agregações sobre o DataFrame ou, se preferir, consultas parametrizadas ao Athena), sempre usando `sales_amount`, `product_line`, `product_name`, `country` e a coluna de data alinhadas ao resultado da consulta da seção 4.4.

**Critérios mínimos de conclusão da Task 3:**

1. Pelo menos três consultas Athena bem-sucedidas: exploração em `dim_products`, totais por país (4.3) e consulta detalhada (4.4).
2. Dashboard no Jupyter com os filtros descritos e gráfico coerente com os filtros e com o Top N.
3. Uso consistente do esquema estrela da Task 2 (tabelas e colunas do contrato), sem depender de SQL contra o RDS da Task 1 para esta etapa.
