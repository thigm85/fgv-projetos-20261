# Data Pipeline com AWS RDS e MySQL

## Descrição

Este projeto implementa um pipeline de engenharia de dados dividido em três etapas:

- Provisionamento de uma instância MySQL no AWS RDS  
- Carga de dados a partir de um arquivo SQL  
- Validação das tabelas, colunas e dados carregados  

A execução é feita de forma sequencial por um script principal.

---

## Estrutura

- `rds_provider.py`: cria a instância RDS e retorna o endpoint  
- `data_loader.py`: cria o banco e executa o script SQL  
- `data_validation.py`: valida as tabelas e seus dados  
- `main.py`: orquestra o pipeline completo  
- `.env`: variáveis de ambiente  
- `requirements.txt`: dependências do projeto  

---

## Pré-requisitos

- Python 3.10 ou superior  
- Conta AWS com permissões para criar RDS  
- AWS CLI configurado (`aws configure`)  

---

## Instalação

Criar ambiente virtual:

```bash
python -m venv venv
source venv/bin/activate
```

Instalar dependências:

```bash
pip install -r requirements.txt
```

---

## Configuração

Criar um arquivo `.env` na raiz do projeto:

```env
AWS_REGION=
DB_INSTANCE_ID=
DB_INSTANCE_CLASS=
DB_ENGINE=
DB_ENGINE_VERSION=
DB_USER=
DB_PASSWORD=
DB_STORAGE=
DB_HOST=
DB_NAME=
DB_PUBLIC=
DB_BACKUP_RETENTION=
PROJECT_NAME=

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
AWS_DEFAULT_REGION=
```

Observações:

- `DB_HOST` não precisa ser definido manualmente  
- O endpoint do banco é obtido automaticamente após a criação do RDS  

---

## Execução

Rodar o pipeline:

```bash
python main.py
```

---

## Fluxo de execução

### 1. Provisionamento do RDS

Arquivo: `rds_provider.py`

- Cria uma instância MySQL no AWS RDS usando `boto3`  
- Aguarda até que a instância esteja disponível  
- Recupera o endpoint de conexão  

---

### 2. Carga de dados

Arquivo: `data_loader.py`

- Conecta ao banco usando o endpoint retornado  
- Cria o banco de dados caso não exista  
- Executa o script SQL informado  
- Cria tabelas e insere dados  

O script SQL é dividido em comandos individuais antes da execução.

---

### 3. Validação

Arquivo: `data_validation.py`

Para cada tabela esperada:

- Verifica se existe  
- Conta o número de registros  
- Lista colunas, tipos e propriedades  

Tabelas verificadas:

- customers  
- products  
- productlines  
- orders  
- orderdetails  
- payments  
- employees  
- offices  

---

## Arquivo SQL

O pipeline espera um arquivo SQL contendo:

- instruções de criação de tabelas  
- inserts de dados  

---

## Detalhes de implementação

### rds_provider.py

- Utiliza `boto3` para criar a instância RDS  
- Usa `waiters` para aguardar disponibilidade  
- Recupera o endpoint via `describe_db_instances`  

---

### data_loader.py

- Utiliza `mysql.connector`  
- Lê o arquivo SQL do disco  
- Divide o script em múltiplos statements com `sqlparse`  
- Executa cada comando sequencialmente  

---

### data_validation.py

- Consulta `INFORMATION_SCHEMA`  
- Verifica estrutura e conteúdo das tabelas  
- Loga inconsistências quando encontradas  

---

## Observações

- A criação do RDS pode levar alguns minutos  
- Executar o pipeline mais de uma vez pode causar erro caso a instância já exista  
- É necessário liberar acesso ao banco (porta 3306) no Security Group da AWS  
- O IP da máquina local deve estar autorizado  
