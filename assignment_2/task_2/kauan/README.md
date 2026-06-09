# Assignment 2 — Task 1: Origem Incremental e Watermark

Este diretório contém a implementação da Task 1 do Assignment 2, preparando o sistema de origem (RDS MySQL) para cargas incrementais de dados.

## Arquitetura e Fluxo da Task 1

O pipeline incremental segue o fluxo de validação e simulação abaixo, orquestrado e demonstrado pelo arquivo central `main.py`:

```text
1. scripts/provision_rds.py        → Garante a infraestrutura do RDS MySQL.
2. scripts/load_data.py            → Reseta o banco de dados e carrega o histórico original.
3. scripts/init_watermark.py       → Inicializa a tabela etl_watermark com a data máxima da carga histórica.
4. validation/validate_incremental_source.py → Valida que o baseline inicial de dados está em dia (sem pendências).
5. scripts/simulate_new_orders.py  → Insere pedidos novos na origem de forma transacional e com datas recentes.
6. validation/validate_incremental_source.py → Revalida a origem para constatar a presença de novos dados pendentes de ETL.
```

---

## Estrutura de Arquivos Organizada

```text
kauan/
├── rds_connection.env           # Configurações de conexão do RDS (gerado automaticamente)
├── .env                         # Credenciais mestras do banco de dados (ignoradas no git)
├── main.py                      # Orquestrador central que executa e demonstra o pipeline completo (raiz)
├── dashboard.ipynb              # Notebook Jupyter para análises e visualizações (raiz)
├── requirements.txt             # Dependências de pacotes Python
├── etl/
│   └── glue_job.py                   # Script de ETL incremental (AWS Glue)
├── terraform/
│   └── (arquivos de definição IAC)   # Configuração de Infraestrutura como Serviço
├── scripts/
│   ├── provision_rds.py              # Script de provisionamento do RDS MySQL
│   ├── load_data.py                  # Script de carga inicial e reset do banco de dados
│   ├── init_watermark.py             # Inicializa a tabela de controle etl_watermark
│   ├── simulate_new_orders.py        # Insere novos pedidos de teste
│   └── run_etl.py                    # Script do orquestrador de ETL (Task 2)
└── validation/
    ├── validation.py                 # Validador geral de schema e consistência física (do Assignment 1)
    ├── validate_incremental_source.py # Validador das datas de watermark e integridade dos novos pedidos
    ├── validate_etl.py               # Validador de dados parquet no S3 e consistência de valores
    └── validate_athena.py            # Validador de consultas Athena
```

---

## Variáveis de Conexão

As credenciais do banco de dados MySQL são lidas dinamicamente do arquivo `rds_connection.env` ou do arquivo `.env`. Importante: Estes arquivos contêm segredos e não devem ser commitados no controle de versão (estão listados no `.gitignore`).

---

## Como Executar

### Execução Completa Automatizada (Recomendado)

O arquivo `main.py` serve como orquestrador central e executa a demonstração do fluxo completo de ponta a ponta:

```bash
# Executa todo o pipeline sequencialmente (provisionamento, carga, watermark, simulação e validações)
python3 main.py
```

### Execuções Individuais e Customizadas

Você também pode utilizar o `main.py` para rodar passos específicos ou parametrizar a simulação:

```bash
# Executa apenas o provisionamento do RDS
python3 main.py --provision

# Executa apenas o reset e a carga de dados histórica
python3 main.py --load-data

# Executa apenas a inicialização do watermark
python3 main.py --init-watermark

# Reseta o watermark para o baseline histórico (sem limpar o banco)
python3 main.py --reset-watermark

# Executa apenas a validação da origem
python3 main.py --validate

# Executa apenas a simulação (ex: gerando 10 pedidos com seed fixa)
python3 main.py --simulate --count 10 --seed 42
```

Caso prefira rodar os arquivos diretamente:
```bash
python3 scripts/provision_rds.py
python3 scripts/load_data.py
python3 scripts/init_watermark.py
python3 validation/validate_incremental_source.py
python3 scripts/simulate_new_orders.py --count 5
```
