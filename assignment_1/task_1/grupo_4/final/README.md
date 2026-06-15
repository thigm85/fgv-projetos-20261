# Task 1 — RDS MySQL + classicmodels (Grupo 4)

Fluxo pedido em [rds.md](../../rds.md): provisionar MySQL no Amazon RDS, carregar o banco de exemplo `classicmodels`, validar tabelas e dados. Opcionalmente deletar a instância RDS logo após.

## Estrutura


| Caminho                                                                      | Função                                                                                          |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| [classicmodels_rds/config.py](classicmodels_rds/config.py)                   | Variáveis de ambiente; caminho padrão do SQL em `task_1/data/`; grava/lê `connection.local.env` |
| [classicmodels_rds/aws_provision.py](classicmodels_rds/aws_provision.py)     | Security group (3306), `create_db_instance`, espera `available`, teardown opcional              |
| [classicmodels_rds/mysql_io.py](classicmodels_rds/mysql_io.py)               | Conexão com retentativas; carga via `cmd_query_iter`; validação das 8 tabelas                   |
| [scripts/a_provision_rds.py](scripts/a_provision_rds.py)                   | Cria SG + instância RDS e grava o endpoint em `connection.local.env`                            |
| [scripts/b_load_classicmodels.py](scripts/b_load_classicmodels.py)         | Executa o arquivo SQL completo no RDS                                                           |
| [scripts/c_validate_classicmodels.py](scripts/c_validate_classicmodels.py) | Confere tabelas e contagens (exit code 1 se falhar)                                             |
| [scripts/d_destroy_rds.py](scripts/d_destroy_rds.py)                       | Remove a instância e o SG do laboratório (opcional)                                             |
| [main.py](main.py)                                                           | Execução completa (provisionamento, carga, validação, opcional teardown)                        |


## Pré-requisitos

- Python 3.10+
- Credenciais AWS com permissões **RDS** e **EC2** (criar/listar/apagar instância RDS e security groups)
- `pip install -r requirements.txt`

## Credenciais AWS

Antes de executar os scripts, configure suas credenciais AWS localmente.

Crie ou edite o seguinte arquivo na raiz da sua máquina:

`~/.aws/credentials`

Com o conteúdo:

```ini
[default]
aws_access_key_id=YOUR_ACCESS_KEY
aws_secret_access_key=YOUR_SECRET_KEY
aws_session_token=YOUR_SESSION_TOKEN
```

Esses valores podem ser obtidos ao inicializar o laboratório, na aba AWS Details (AWS CLI).

## Configuração

1. Copie `.env.example` para `.env` e defina pelo menos `RDS_MASTER_PASSWORD`;
2. Após o passo 1 de provisionamento, `connection.local.env` é criado na mesma pasta com `DB_HOST` / `RDS_ENDPOINT`. Esse ficheiro está no `.gitignore`.

O dump SQL por omissão resolve para `assignment_1/task_1/data/mysqlsampledatabase.sql`. Pode sobrepor com `SQL_FILE_PATH`.


## Execução (ordem)

```bash
cd grupo_4/final
python scripts/a_provision_rds.py
python scripts/b_load_classicmodels.py
python scripts/c_validate_classicmodels.py
```

Teardown opcional:

```bash
python scripts/d_destroy_rds.py
```

O arquivo `main.py` executa todos os scripts em ordem.

```sh
python main.py
```

## Carga do SQL

O script usa **mysql-connector-python** e `MySQLConnection.cmd_query_iter()` para enviar o script multi-declaração e consumir todos os resultados, sem depender do cliente `mysql` na shell.

## Segurança

O security group criado abre a porta **3306** a `0.0.0.0/0` para facilitar acesso a partir da sua máquina. **Isso não deve ser feito em produção**: restrinja ao seu IP ou à VPC.

A conexão MySQL usa `ssl_disabled=True` para reduzir fricção no lab; em produção use TLS com o bundle de CA da AWS.

## Versão do motor

Se `RDS_ENGINE_VERSION` falhar na criação (versão indisponível na região), ajuste o valor no `.env` para uma versão listada no console RDS para MySQL 8.0.