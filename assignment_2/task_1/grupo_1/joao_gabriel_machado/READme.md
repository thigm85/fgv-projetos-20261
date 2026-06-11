# Assignment 2 — Task 1: Origem Incremental e Watermark

## 1. Configuração de Segurança (.env)

Para garantir a segurança do banco de dados e evitar o vazamento de credenciais no controle de versão (Git), este projeto utiliza variáveis de ambiente. 

Crie um arquivo chamado `.env` dentro da pasta `sql/` com o formato do arquivo `sql/.env.example`

```env
# Identificador do banco de dados no RDS
DB_IDENTIFIER=sales-analytics-db

# Usuário de acesso ao banco
DB_USER=admin

# Senha de acesso ao banco
DB_PASSWORD=sua_senha_aqui

# ID do Security Group configurado no Terraform
SECURITY_GROUP_ID=sg-xxxxxxxxxxxxxxxx

# Endpoint do host
DB_HOST=sales-analytics-db.xxxxxxxxxxxx.us-east-1.rds.amazonaws.com
```

O uso do `.env` impede que senhas sejam enviadas para o repositórios final, seguindo as melhores práticas de Engenharia de Software e Segurança da Informação.

---

## 2. Fluxo de Execução

Os scripts devem ser executados na sequência abaixo, a partir do diretório `sql/`.

### Inicializar o Watermark

Cria a tabela de controle `etl_watermark` e registra a data do último pedido já processado no Assignment 1.

```bash
python init_watermark.py

```

### Simular Novos Pedidos

Simula a operação contínua da loja, gerando novos pedidos de forma transacional. 

```bash
# Simula a criação de 5 novos pedidos (padrão)
python simulate_new_orders.py --count 5

# Simula a criação com uma seed e count 10
python simulate_new_orders.py --count 10 --seed 42
```

### Validação

Verifica a integridade do banco de dados antes que o AWS Glue inicie a extração.

```bash
python validate_incremental_source.py
```