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

---

## 3. Especificações Técnicas e Evidências (Task 2)

### 3.1. Arquitetura de Permissões IAM (Critério 3.1.2)
Como o ambiente de avaliação utiliza uma estrutura de laboratório de Academy (**AWS Academy / Learner Lab**), não conseguimos criar e anexar políticas IAM customizadas ao serviço do EventBridge devido a bloqueios de segurança (`AccessDenied`).
* **Solução Adotada:** Configuramos o recurso `aws_cloudwatch_event_target` no Terraform para invocar os serviços reutilizando a **`LabRole`** nativa da conta. Como a `LabRole` já possui permissões administrativas completas sobre o ecossistema do AWS Glue (`glue:*`), o EventBridge obteve autorização imediata para disparar nossa pipeline de forma segura e automatizada.
* **Orquestração de Destino:** Devido a restrições estritas da API da AWS, o EventBridge foi configurado para disparar um **Glue Workflow** (`aws_glue_workflow`), que atua como uma ponte para engatilhar o nosso Job incremental de PySpark (`aws_glue_job`).

### 3.2. Relatório de Coerência Incremental e Volumetria (Critério 3.4.2)
Após a execução sequencial do simulador e da pipeline na nuvem, o comportamento analítico do Data Lake validou o sucesso do modelo incremental:
1. **Filtro de Janela Limpa:** O Job do Glue extraiu estritamente os dados onde `orders.orderDate > 2005-05-31` (último Watermark registrado), ignorando completamente o reprocessamento de dados históricos e poupando custos de rede.
2. **Consistência de Carga:** O volume de linhas adicionadas ao prefixo `data/fact_orders/` no S3 foi auditado pelo script `validate_post_incremental.py` e mostrou equivalência matemática exata com o número de registros injetados pelo script de simulação.
3. **Persistência de Regras de Negócio:** O cálculo da métrica de faturamento analítico (`sales_amount = quantity_ordered * price_each`) manteve-se perfeitamente íntegro e preciso para todas as novas linhas agregadas no Data Lake, sem divergências de ponto flutuante.

As métricas brutas e logs de sucesso gerados nesta auditoria podem ser inspecionados no arquivo de evidência local: `sql/validation_post_incremental.txt`.