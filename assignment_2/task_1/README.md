# Assignment 2 — Task 1: Origem Incremental e Watermark

## Visão Geral

Este diretório contém scripts para preparar o sistema de origem (RDS MySQL) para cargas incrementais de dados. Implementa:

1. **Tabela de Watermark** (`etl_watermark`) para rastrear o estado do ETL
2. **Simulação de Novos Pedidos** para testar o pipeline sem depender de dados externos
3. **Validação do Sistema** para garantir que tudo está pronto para a Task 2

## Estrutura de Diretórios

```
task_1/
├── scripts/
│   ├── init_watermark.py              # Inicializa tabela de watermark
│   ├── simulate_new_orders.py         # Simula novos pedidos
│   └── validate_incremental_source.py # Valida preparação para ETL
├── sql/
│   └── (scripts SQL adicionais, se necessário)
├── config.py                          # Configuração centralizada de RDS
├── requirements.txt                   # Dependências Python
└── README.md                          # Este arquivo
```

## Pré-requisitos

1. **Assignment 1 concluído**: A instância RDS com banco `classicmodels` já deve estar criada e populada.
2. **Python 3.8+** com pip
3. **Credenciais AWS** configuradas (via `~/.aws/credentials` ou variáveis de ambiente)
4. **Variáveis de Ambiente** (opcional, para override de defaults):
   - `AWS_DEFAULT_REGION`: Região AWS (padrão: `us-east-1`)
   - `RDS_PASSWORD`: Senha do usuário `admin` no RDS (padrão: `ClassicModels2026!`)

## Instalação

### 1. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar Credenciais AWS (se necessário)

**Linux/macOS/Git Bash:**
```bash
# Opção 1: Arquivo de configuração
aws configure

# Opção 2: Variáveis de ambiente
export AWS_ACCESS_KEY_ID="sua-access-key"
export AWS_SECRET_ACCESS_KEY="sua-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
export RDS_PASSWORD="sua-senha-rds"
```

**Windows PowerShell:**
```powershell
# Opção 1: Arquivo de configuração
aws configure

# Opção 2: Variáveis de ambiente (sessão atual)
$env:AWS_ACCESS_KEY_ID="sua-access-key"
$env:AWS_SECRET_ACCESS_KEY="sua-secret-key"
$env:AWS_DEFAULT_REGION="us-east-1"
$env:RDS_PASSWORD="sua-senha-rds"

# Depois execute os scripts:
python scripts/init_watermark.py
```

## Fluxo de Execução Recomendado

### Passo 1: Inicializar Watermark

Cria a tabela `etl_watermark` e inicializa com a data máxima de pedidos existentes:

```bash
python scripts/init_watermark.py
```

**Saída esperada:**
```
Conectando ao RDS: classic-models-db.xxxx.rds.amazonaws.com:3306
Criando/verificando tabela 'etl_watermark'...
OK: Tabela 'etl_watermark' pronta.
MAX(orders.orderDate) encontrado: 2005-06-09
OK: Pipeline 'classicmodels_sales' inicializado com watermark em 2005-06-09.

INICIALIZAÇÃO DE WATERMARK CONCLUÍDA COM SUCESSO!
```

### Passo 2: Validar Estado Inicial

Verifica que o sistema está pronto antes de simular dados:

```bash
python scripts/validate_incremental_source.py
```

**Saída esperada:**
```
==============================================================
VALIDAÇÃO DO SISTEMA DE ORIGEM INCREMENTAL
==============================================================

[CHECK 1/4] Verificando existência da tabela 'etl_watermark'...
  ✓ Tabela 'etl_watermark' existe.

[CHECK 2/4] Verificando registro do pipeline 'classicmodels_sales'...
  ✓ Pipeline 'classicmodels_sales' encontrado em watermark.

[CHECK 3/4] Verificando validade do watermark...
  ✓ Watermark válido: 2005-06-09 (status: NEVER_RUN)

[CHECK 4/4] Verificando disponibilidade de dados incrementais...
  ⚠ Sem dados incrementais: MAX(orderDate) = 2005-06-09, watermark = 2005-06-09
    (OK durante testes iniciais; execute simulate_new_orders.py para gerar dados)

==============================================================
RESULTADO: 4/4 verificações passadas
==============================================================

✓ VALIDAÇÃO OK: Sistema de origem pronto para cargas incrementais!
```

### Passo 3: Simular Novos Pedidos

Insere novos pedidos com datas posteriores ao watermark:

```bash
# Simular 5 pedidos (padrão)
python scripts/simulate_new_orders.py

# Simular 10 pedidos
python scripts/simulate_new_orders.py --count 10

# Simular com seed para reprodutibilidade
python scripts/simulate_new_orders.py --count 5 --seed 42
```

**Saída esperada:**
```
Conectando ao RDS: classic-models-db.xxxx.rds.amazonaws.com:3306
Seed definida para reprodutibilidade: 42
Found 122 active customers and 110 products.
Watermark atual: 2005-06-09

Inserindo 5 novos pedidos...
  [1/5] Ordem #10425 criada (data: 2005-06-10, cliente: 112)
  [2/5] Ordem #10426 criada (data: 2005-06-13, cliente: 214)
  [3/5] Ordem #10427 criada (data: 2005-06-14, cliente: 119)
  [4/5] Ordem #10428 criada (data: 2005-06-17, cliente:298)
  [5/5] Ordem #10429 criada (data: 2005-06-20, cliente: 103)

============================================================
RESUMO DA SIMULAÇÃO
============================================================
Pedidos criados: 5
IDs dos pedidos: [10425, 10426, 10427, 10428, 10429]
Linhas em orderdetails criadas: 5
Faixa de datas: 2005-06-10 a 2005-06-20
============================================================
SIMULAÇÃO CONCLUÍDA COM SUCESSO!
```

### Passo 4: Validar Após Simulação

Verifica que há dados novos pendentes de ETL:

```bash
python scripts/validate_incremental_source.py
```

**Saída esperada:**
```
[CHECK 4/4] Verificando disponibilidade de dados incrementais...
  ✓ Dados novos disponíveis: 5 pedidos após 2005-06-09
```

## Contrato do Banco de Dados

### Tabela `etl_watermark`

```sql
CREATE TABLE IF NOT EXISTS `etl_watermark` (
    `pipeline_name` VARCHAR(64) PRIMARY KEY,
    `last_processed_order_date` DATE NOT NULL,
    `last_run_at` DATETIME NOT NULL,
    `last_run_status` VARCHAR(32) NOT NULL DEFAULT 'NEVER_RUN'
);
```

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `pipeline_name` | `VARCHAR(64)` | Identificador único do pipeline (PK). Valor fixo: `classicmodels_sales` |
| `last_processed_order_date` | `DATE` | Maior `orders.orderDate` já refletida no lake analítico |
| `last_run_at` | `DATETIME` | Timestamp UTC da última execução bem-sucedida |
| `last_run_status` | `VARCHAR(32)` | Status: `NEVER_RUN`, `SUCCEEDED`, `FAILED` |

## Scripts

### `init_watermark.py`

**Responsabilidades:**
- Cria tabela `etl_watermark` se não existir
- Insere registro inicial com `pipeline_name = 'classicmodels_sales'`
- Inicializa `last_processed_order_date` com `MAX(orders.orderDate)`
- Idempotente: múltiplas execuções não causam erros

**Opções:**
- Nenhuma (sem argumentos CLI)

**Exit Codes:**
- `0`: Sucesso
- `1`: Erro ao conectar ou executar SQL

---

### `simulate_new_orders.py`

**Responsabilidades:**
- Lê `last_processed_order_date` do watermark
- Insere N pedidos com datas posteriores (dias úteis)
- Insere linhas correspondentes em `orderdetails`
- **NÃO atualiza o watermark** (responsabilidade do Job Glue)
- Usa transações para garantir consistência

**Opções:**
```bash
--count N    : Número de pedidos a simular (padrão: 5)
--seed N     : Seed para reprodutibilidade de random (opcional)
```

**Exemplo:**
```bash
python scripts/simulate_new_orders.py --count 10 --seed 123
```

**Exit Codes:**
- `0`: Sucesso
- `1`: Erro ao conectar, dados insuficientes, ou erro SQL

---

### `validate_incremental_source.py`

**Responsabilidades:**
- Verifica existência de `etl_watermark`
- Verifica presença de `pipeline_name = 'classicmodels_sales'`
- Valida que `last_processed_order_date` não é NULL
- Verifica integridade de `orders` e `orderdetails`
- Retorna exit code `0` se **todas** as checagens passarem

**Checagens Realizadas:**
1. ✓ Tabela `etl_watermark` existe
2. ✓ Pipeline `classicmodels_sales` está registrado
3. ✓ `last_processed_order_date` é válido (não NULL)
4. ✓ Há dados novos ou baseline é consistente
5. ✓ Integridade de `orderdetails` para novos pedidos

**Exit Codes:**
- `0`: Todas as validações passaram
- `1`: Uma ou mais validações falharam

---

## Troubleshooting

### Erro: "Tabela 'orders' está vazia"

**Causa:** Assignment 1 não foi concluído com sucesso.

**Solução:**
```bash
cd ../../assignment_1/task_1/arroio_do_sal/guilherme_buss/
python provision_rds.py
python load_data.py
cd ../../../../assignment_2/task_1
```

---

### Erro: "Pipeline 'classicmodels_sales' não encontrado em watermark"

**Causa:** `init_watermark.py` não foi executado após Assignment 1.

**Solução:**
```bash
python scripts/init_watermark.py
```

---

### Erro: "Conexão recusada" ou Timeout

**Causa:** Instância RDS não está disponível ou credenciais incorretas.

**Solução:**
1. Verifique se a instância RDS está em status `available`:
   ```bash
   aws rds describe-db-instances --db-instance-identifier classic-models-db --region us-east-1
   ```
2. Verifique credenciais:
   ```bash
   export AWS_ACCESS_KEY_ID="seu-key"
   export AWS_SECRET_ACCESS_KEY="sua-secret"
   export RDS_PASSWORD="sua-senha"
   ```

---

### Erro: "AccessDenied" ou "UnauthorizedOperation"

**Causa:** Credenciais AWS sem permissão para RDS.

**Solução:**
- Verifique se o usuário IAM tem políticas `rds:DescribeDBInstances` e `rds:ModifyDBInstance`
- Use credenciais com permissões adequadas

---

## Notas Importantes

1. **Sem Atualização de Watermark na Task 1**: O script `simulate_new_orders.py` **não atualiza** `last_run_at` ou `last_run_status` no watermark. Isso é responsabilidade do job Glue na Task 2 para evitar condição de corrida.

2. **Reprodutibilidade**: Use `--seed` para garantir resultados consistentes durante testes:
   ```bash
   python scripts/simulate_new_orders.py --count 5 --seed 42
   ```

3. **Datas de Pedidos**: Os pedidos simulados sempre usam **dias úteis** (segunda a sexta) para facilitar particionamento por data na Task 2.

4. **Consistência de Dados**: Cada pedido criado tem:
   - Uma linha em `orders`
   - Pelo menos uma linha correspondente em `orderdetails`
   - `quantityOrdered * priceEach` consistente com regras de negócio

5. **Idempotência**: `init_watermark.py` é idempotente (múltiplas execuções são seguras). `simulate_new_orders.py` cria novos pedidos a cada execução (não é idempotente).

## Próximas Etapas

Após concluir com sucesso os 4 passos acima:
- Proceda para **Assignment 2 — Task 2**: Implemente o job Glue para consumir dados incrementais
- A Task 2 atualizará a coluna `last_run_at` e `last_run_status` no watermark após sucesso

## Referências

- [MySQL Sample Database Documentation](https://www.mysqltutorial.org/mysql-sample-database.aspx)
- [PyMySQL Documentation](https://pymysql.readthedocs.io/)
- [AWS RDS with Python and Boto3](https://docs.aws.amazon.com/code-samples/latest/catalog/code-catalog-python-rds.html)
