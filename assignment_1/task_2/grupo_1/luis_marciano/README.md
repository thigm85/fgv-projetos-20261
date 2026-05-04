# ClassicModels Data Pipeline

Implementação completa das Tasks 1 e 2 do projeto de Data Engineering, criando um pipeline ETL que extrai dados de um banco MySQL OLTP, transforma em esquema estrela e carrega em formato Parquet no Amazon S3.

## 📁 Estrutura do Projeto

```
luis_marciano/
├── config/                    # Arquivos de configuração
│   ├── .env.example          # Exemplo de variáveis de ambiente AWS
│   ├── requirements.txt      # Dependências Python
│   └── rds_config.txt        # Configurações de conexão RDS (gerado)
├── scripts/                  # Scripts Python de automação
│   ├── generate_config.py   # Gera configuração de conexão RDS
│   ├── load_data.py         # Carrega dados de exemplo no RDS
│   ├── validate.py          # Valida dados carregados no RDS
│   ├── extract_to_s3.py     # Extrai dados RDS → CSV no S3
│   ├── etl_transform.py     # Script PySpark para transformação ETL
│   └── validate_etl.py      # Valida dados transformados no S3
├── terraform/                # Infraestrutura como código
│   ├── main.tf              # Recursos AWS (RDS, S3, Glue)
│   ├── variables.tf         # Variáveis Terraform
│   ├── outputs.tf           # Outputs dos recursos
│   ├── terraform.tfvars     # Valores das variáveis (configurado)
│   └── terraform.tfvars.example # Exemplo de configuração
├── README.md                # Este arquivo de documentação
├── .gitignore               # Arquivos ignorados pelo Git
├── .terraform/              # Estado local do Terraform
├── terraform.tfstate*       # Estado dos recursos AWS
└── venv/                    # Ambiente virtual Python
```

## 🎯 Visão Geral das Tasks

### Task 1: Sistema de Origem (OLTP)
- **Objetivo**: Configurar banco MySQL no RDS com dados de exemplo
- **Dados**: ClassicModels (vendas de miniaturas de carros/modelos)
- **Ferramentas**: Terraform, Python, MySQL

### Task 2: Pipeline ETL
- **Objetivo**: Extrair dados OLTP → Transformar em Star Schema → Carregar no S3
- **Arquitetura**: AWS Glue + PySpark + S3
- **Resultado**: Dados analíticos em Parquet otimizados para consultas

## 🚀 Guia de Execução

### Pré-requisitos
- **AWS CLI** configurado com credenciais válidas
- **Terraform** v1.0+
- **Python** 3.8+
- **Git** para controle de versão

### 1. Configuração Inicial

```bash
# Clonar ou navegar para o projeto
cd /Users/luis.marciano/fgv-projetos-20261/assignment_1/task_2/grupo_1/luis_marciano

# Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install -r config/requirements.txt
```

### 2. Configurar Credenciais AWS

```bash
# Copiar arquivo de exemplo
cp config/.env.example .env

# Editar .env com suas credenciais AWS
# OU usar aws configure
aws configure
```

### 3. Provisionar Infraestrutura (Task 1)

```bash
# Navegar para pasta Terraform
cd terraform

# Inicializar Terraform
terraform init

# Planejar mudanças
terraform plan

# Aplicar infraestrutura
terraform apply
```

**Recursos criados:**
- ✅ RDS MySQL instance (`classicmodels-db`)
- ✅ Security Group para acesso MySQL
- ✅ S3 Bucket (`classicmodels-data-lake`)
- ✅ Glue Catalog Database
- ✅ Glue ETL Job

### 4. Carregar Dados de Exemplo

```bash
# Gerar configuração de conexão
python3 scripts/generate_config.py

# Carregar dados no RDS
python3 scripts/load_data.py

# Validar carga dos dados
python3 scripts/validate.py
```

### 5. Executar Pipeline ETL (Task 2)

```bash
# Extrair dados do RDS para S3 (CSV)
python3 scripts/extract_to_s3.py

# Executar job Glue ETL
aws glue start-job-run --job-name classicmodels-etl

# Aguardar conclusão (~2-3 minutos)
aws glue get-job-run --job-name classicmodels-etl --run-id <JOB_RUN_ID>

# Validar dados transformados
python3 scripts/validate_etl.py classicmodels-data-lake
```

## 📊 Esquema de Dados

### Origem (OLTP - MySQL)
- **customers**: 122 registros
- **products**: 110 registros
- **productlines**: 7 registros
- **orders**: 326 registros
- **orderdetails**: 2.996 registros
- **offices**: 7 registros

### Destino (Star Schema - Parquet/S3)

#### Tabela Fato
**fact_orders** (2.996 registros)
- `order_id`: ID do pedido
- `customer_id`: FK para dim_customers
- `product_id`: FK para dim_products
- `order_date_key`: FK para dim_dates
- `country_key`: FK para dim_countries
- `quantity_ordered`: Quantidade pedida
- `price_each`: Preço unitário
- `sales_amount`: Valor total (quantity × price)

#### Tabelas Dimensão
**dim_customers** (122 registros)
- `customer_id`, `customer_name`, `contact_name`, `city`, `country`

**dim_products** (117 registros)
- `product_id`, `product_name`, `product_line`, `product_vendor`

**dim_dates** (265 registros)
- `date_key`, `full_date`, `year`, `quarter`, `month`, `day`

**dim_countries** (28 registros)
- `country_key`, `country`, `territory`

## 🔧 Comandos Úteis

### Terraform
```bash
# Ver estado dos recursos
cd terraform && terraform show

# Destruir infraestrutura
cd terraform && terraform destroy

# Ver outputs
cd terraform && terraform output
```

### AWS CLI
```bash
# Listar conteúdo do S3
aws s3 ls s3://classicmodels-data-lake/ --recursive

# Verificar status do Glue Job
aws glue get-job --job-name classicmodels-etl

# Logs do CloudWatch
aws logs tail /aws-glue/jobs/output --since 1h
```

### Python Scripts
```bash
# Todos os scripts aceitam --help para mais informações
python3 scripts/generate_config.py --help
```

## 🏗️ Arquitetura Técnica

```
[MySQL RDS] → [Python ETL] → [CSV no S3] → [Glue PySpark] → [Parquet Star Schema no S3]
     ↑               ↑             ↑                    ↑
   OLTP           Extração     Armazenamento       Transformação
   Dados         Local → S3    Temporário         Star Schema
   Transacionais               Raw Data           Analítico
```

### Decisões de Design
- **Glue Connection**: Removida devido a limitações de rede no ambiente lab
- **Extração Híbrida**: Python local para RDS → CSV, Glue para transformação
- **Star Schema**: Granularidade em nível de linha de pedido (orderdetail)
- **Formato**: Parquet com compressão Snappy para analytics
- **Particionamento**: Não implementado (dados pequenos do ClassicModels)

## ✅ Validações Implementadas

### Task 1 (RDS)
- ✅ Conexão com banco estabelecida
- ✅ Tabelas criadas e populadas
- ✅ Contagem de registros por tabela
- ✅ Relacionamentos íntegros

### Task 2 (ETL)
- ✅ Job Glue executado com SUCCEEDED
- ✅ Arquivos Parquet criados no S3
- ✅ Esquema star correto
- ✅ Cálculo sales_amount = quantity × price
- ✅ Integridade referencial mantida

## 🧹 Limpeza de Recursos

```bash
# Destruir infraestrutura AWS
cd terraform && terraform destroy

# Remover arquivos locais (opcional)
rm -rf .terraform terraform.tfstate* venv/
```

## 📝 Notas Importantes

- **Ambiente Lab**: Algumas limitações de IAM requereram ajustes na arquitetura
- **Custos**: Monitore uso do RDS (free tier) e Glue (pago por execução)
- **Segurança**: Credenciais em `.env` não devem ser commitadas
- **Performance**: Pipeline otimizado para dados pequenos (ClassicModels)

## 🤝 Contribuição

1. Faça fork do projeto
2. Crie uma branch para sua feature
3. Commit suas mudanças
4. Push para a branch
5. Abra um Pull Request

## 📄 Licença

Este projeto é parte de um trabalho acadêmico da FGV.
```

### 4. Executar ETL no Glue
```bash
aws glue start-job-run --job-name classicmodels-etl
```

### 5. Validar Resultados
```bash
python3 validate_etl.py classicmodels-data-lake
```

## Validação dos Resultados

✅ **Job Glue**: SUCCEEDED  
✅ **Arquivos Parquet**: Criados no S3 (fact_orders + 4 dimensões)  
✅ **Integridade de Dados**: sales_amount = quantity_ordered × price_each  
✅ **Integridade Referencial**: Chaves estrangeiras válidas  

## Limpeza

```bash
terraform destroy
```

## Notas Técnicas

- **Limitações do Lab**: Glue não consegue conectar diretamente ao RDS devido a restrições de rede
- **Solução**: Extração local para CSV no S3, depois processamento no Glue
- **Formato**: Parquet com compressão Snappy para eficiência
- **Validação**: Script automatizado verifica todos os critérios de avaliação