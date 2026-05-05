# Task 1 - Notas de Aula Baseadas em Gaps

Objetivo destas notas: transformar os principais gaps observados nas soluções dos grupos em material de aula acionável, mostrando:
- o gap e seu risco;
- como o grupo que melhor tratou o tema abordou o problema;
- a solução ideal recomendada (distinguindo laboratório e produção).

---

## 1) Gap: Idempotência no Provisionamento de RDS

**Gap identificado**  
Múltiplas soluções falham em reexecução segura: tentam criar recursos sem checar existência prévia, sem tratar duplicidade, ou sem estados intermediários (`creating`, `modifying`).

**Como o melhor grupo endereçou**  
O **Grupo 4** tratou melhor este ponto com fluxo idempotente em provisionamento Python (reuso de recursos, tratamento de `already exists`, espera até `available` e teardown explícito).  
O **Grupo 2** também mostrou boa base com reuso de SG e instância.

**Solução ideal recomendada**  
- **Lab:** sempre `describe` antes de `create`, tratar erros conhecidos de duplicidade e aguardar `available` com timeout explícito.  
- **Produção:** além disso, usar estratégia transacional de infraestrutura (IaC + controles de drift), logs estruturados, retries com jitter e políticas de rollback/cleanup.

**Sugestão de rubric de correção (0-3)**  
- `0`: cria recurso sempre sem checar estado.  
- `1`: checa parcialmente (ex.: só instância).  
- `2`: checa recursos-chave + espera pronta.  
- `3`: idempotência completa + tratamento de falhas/reexecução.

**Exemplo do gap (Grupo 1)**  
```python
# solution_task_1_group_1/provision.py
response = rds.create_db_instance(
    DBInstanceIdentifier=DB_INSTANCE_ID,
    AllocatedStorage=20,
    DBInstanceClass='db.t3.micro',
    Engine='mysql',
    MasterUsername=DB_USER,
    MasterUserPassword=DB_PASSWORD,
    PubliclyAccessible=True
)
```

**Exemplo do melhor grupo (Grupo 4)**  
```python
# solution_task_1_group_4/classicmodels_rds/aws_provision.py
try:
    rds.create_db_instance(...)
except ClientError as exc:
    if exc.response["Error"]["Code"] == "DBInstanceAlreadyExists":
        print("[RDS] Instance already exists; waiting for available state ...")
    else:
        raise

waiter = rds.get_waiter("db_instance_available")
waiter.wait(DBInstanceIdentifier=ident, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
```

**Exemplo ideal (produção)**  
```python
def ensure_db_instance(rds, cfg):
    try:
        db = rds.describe_db_instances(DBInstanceIdentifier=cfg.identifier)["DBInstances"][0]
        return db["DBInstanceStatus"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "DBInstanceNotFound":
            raise

    rds.create_db_instance(DBInstanceIdentifier=cfg.identifier, Engine="mysql", ...)
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(DBInstanceIdentifier=cfg.identifier, WaiterConfig={"Delay": 20, "MaxAttempts": 90})
    return "available"
```

---

## 2) Gap: Segurança de Rede (SG/CIDR e exposição da porta 3306)

**Gap identificado**  
Uso recorrente de `0.0.0.0/0` para MySQL e regras permanentes sem escopo temporal, elevando risco de exposição desnecessária.

**Como o melhor grupo endereçou**  
O **Grupo 2** foi o que mais avançou no cenário de laboratório ao tentar restringir acesso ao IP público atual (`/32`) em vez de abrir para toda internet.

**Solução ideal recomendada**  
- **Lab:** restringir ingress para IP atual (`x.x.x.x/32`), com atualização controlada e remoção ao final do exercício.  
- **Produção:** evitar exposição pública; acesso privado (VPC/subnets), bastion ou SSM, regras mínimas por origem/porta, e monitoramento/auditoria de SG.

**Sugestão de rubric de correção (0-3)**  
- `0`: `0.0.0.0/0` sem justificativa/controle.  
- `1`: restrição parcial ou manual inconsistente.  
- `2`: uso de `/32` e processo de revisão de regra.  
- `3`: desenho seguro fim a fim (privado + least privilege).

**Exemplo do gap (Grupo 1)**  
```python
# solution_task_1_group_1/open_port.py
ec2.authorize_security_group_ingress(
    GroupId=sg_id,
    IpProtocol='tcp',
    FromPort=3306,
    ToPort=3306,
    CidrIp='0.0.0.0/0'
)
```

**Exemplo do melhor grupo (Grupo 2)**  
```python
# solution_task_1_group_2/provision_rds.py
cidr = f"{my_ip}/32"
ec2.authorize_security_group_ingress(
    GroupId=sg_id,
    IpPermissions=[{
        "IpProtocol": "tcp",
        "FromPort": 3306,
        "ToPort": 3306,
        "IpRanges": [{"CidrIp": cidr, "Description": f"Acesso {time.time()}"}],
    }],
)
```

**Exemplo ideal (produção)**  
```hcl
# terraform
resource "aws_security_group_rule" "mysql_from_app" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.app.id
  description              = "Only app tier can access MySQL"
}
```

---

## 3) Gap: Gestão de Configuração e Segredos

**Gap identificado**  
Hardcoding de host/usuário/senha em scripts, arquivos locais com segredo em texto puro e baixa portabilidade entre ambientes.

**Como o melhor grupo endereçou**  
O **Grupo 4** apresentou melhor organização de configuração (módulo dedicado, `.env` + arquivo local de conexão e separação de responsabilidades).  
O **Grupo 5** também se destacou por flexibilidade de aliases de variáveis.

**Solução ideal recomendada**  
- **Lab:** `.env.example` sem segredos reais, leitura centralizada de variáveis, validação de obrigatórias, sem hardcode.  
- **Produção:** segredos em Secrets Manager/Parameter Store, rotação de credenciais, princípio de mínimo privilégio e proibição de segredo em código/repositório.

**Sugestão de rubric de correção (0-3)**  
- `0`: credenciais hardcoded em código.  
- `1`: parte em env, parte hardcoded.  
- `2`: configuração centralizada e validada.  
- `3`: configuração segura e portável (com práticas de segredos).

**Exemplo do gap (Grupo 2)**  
```python
# solution_task_1_group_2/provision_rds.py
CONFIG = {
    "db_user": "admin",
    "db_password": "FGV_Projetos_2026!",
    "region": "us-east-1",
}
```

**Exemplo do melhor grupo (Grupo 5)**  
```python
# solution_task_1_group_5/01_instance.py
def env_any(names, default=None, required=False):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and not default:
        raise RuntimeError(f"Variável obrigatória ausente: {', '.join(names)}")
    return default or ""
```

**Exemplo ideal (produção)**  
```python
import boto3, json, os

def get_secret(secret_name: str, region: str) -> dict:
    sm = boto3.client("secretsmanager", region_name=region)
    payload = sm.get_secret_value(SecretId=secret_name)["SecretString"]
    return json.loads(payload)

db_cfg = get_secret(os.environ["DB_SECRET_NAME"], os.environ["AWS_REGION"])
db_user = db_cfg["username"]
db_password = db_cfg["password"]
```

---

## 4) Gap: Robustez da Carga de Dados (transação, erro, retries)

**Gap identificado**  
Cargas sem rollback explícito, mensagens de erro pouco diagnósticas, caminhos frágeis para SQL e ausência de retries em cenários instáveis pós-provisionamento.

**Como o melhor grupo endereçou**  
O **Grupo 4** tratou bem robustez operacional (retries de conexão, execução multi-statement com controle, separação em camada de IO).  
O **Grupo 5** também mostrou bom tratamento transacional e fallback de endpoint.

**Solução ideal recomendada**  
- **Lab:** validar caminho SQL com fallback claro, executar em transação (`commit/rollback`), capturar erro com contexto, e fechar recursos sempre.  
- **Produção:** retries com backoff/jitter, idempotência na carga, telemetria de execução e estratégia de reprocessamento.

**Sugestão de rubric de correção (0-3)**  
- `0`: carga sem transação e sem tratamento de erro.  
- `1`: transação básica ou erro básico.  
- `2`: transação + erros claros + recursos fechados corretamente.  
- `3`: robustez completa (retry, observabilidade, reprocesso).

**Exemplo do gap (Grupo 1)**  
```python
# solution_task_1_group_1/load_data.py
with open(SQL_PATH, 'r', encoding='utf-8') as arquivo:
    sql = arquivo.read()

cursor.execute(sql)
conexao.commit()
conexao.close()
```

**Exemplo do melhor grupo (Grupo 4)**  
```python
# solution_task_1_group_4/classicmodels_rds/mysql_io.py
for attempt in range(1, settings.mysql_connect_retries + 1):
    try:
        conn = mysql.connector.connect(...)
        return conn
    except mysql_errors.Error as exc:
        if attempt == settings.mysql_connect_retries:
            break
        time.sleep(settings.mysql_connect_delay_seconds)
```

**Exemplo ideal (produção)**  
```python
def run_load_with_tx(conn, sql_text):
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for stmt in split_statements(sql_text):
                cur.execute(stmt)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("load_failed", extra={"error": str(exc)})
        raise
    finally:
        conn.close()
```

---

## 5) Gap: Validação sem Critérios de Aprovação Objetivos

**Gap identificado**  
Várias soluções apenas imprimem tabelas/contagens, sem regras formais de aceitação, sem checks de integridade e sem `exit code` determinístico.

**Como o melhor grupo endereçou**  
O **Grupo 2** foi referência em profundidade de validação (integridade referencial, regras de negócio, duplicidade e saída com falha quando necessário).  
O **Grupo 4** também avançou com validação estrutural detalhada.

**Solução ideal recomendada**  
- **Lab:** validar conjunto de tabelas esperadas, thresholds mínimos por tabela crítica, checks básicos de integridade e retorno `0/1` consistente.  
- **Produção:** quality gates versionados, testes de contrato de dados, validações incrementais e alertas automatizados.

**Sugestão de rubric de correção (0-3)**  
- `0`: validação apenas visual/informativa.  
- `1`: valida presença de tabelas.  
- `2`: presença + contagem mínima + `exit code`.  
- `3`: presença + integridade + regras de qualidade robustas.

**Exemplo do gap (Grupo 1)**  
```python
# solution_task_1_group_1/validate.py
cursor.execute(f"select table_name from information_schema.tables where table_schema = '{DB_NAME}'")
tabelas = cursor.fetchall()

for tabela in tabelas:
    nome_tabela = tabela[0]
    cursor.execute(f"select count(*) from `{nome_tabela}`")
    print(f"Tabela: {nome_tabela} | Total de Registros: {cursor.fetchone()[0]}")
```

**Exemplo do melhor grupo (Grupo 2)**  
```python
# solution_task_1_group_2/validation.py
def check_foreign_keys(conn):
    for desc, query in FK_CHECKS:
        orphans = scalar(conn, query)
        if orphans == 0:
            ok(desc)
        else:
            fail(f"{desc} -> {orphans} registro(s) órfão(s)")
```

**Exemplo ideal (produção)**  
```python
def validate_quality(conn) -> int:
    failures = []
    failures += assert_expected_tables(conn, expected_tables)
    failures += assert_minimum_row_counts(conn, thresholds)
    failures += assert_fk_integrity(conn, fk_checks)
    if failures:
        for item in failures:
            logger.error("quality_gate_failed", extra=item)
        return 1
    return 0
```

---

## 6) Gap: Observabilidade e Operabilidade do Pipeline

**Gap identificado**  
Ausência frequente de `--dry-run`, logs de etapa padronizados e mensagens orientadas a troubleshooting; isso reduz previsibilidade e dificulta suporte.

**Como o melhor grupo endereçou**  
O **Grupo 5** destacou-se por logs de progresso em etapas e melhor clareza operacional no fluxo.  
O **Grupo 4** também teve boa organização e separação de componentes para manutenção.

**Solução ideal recomendada**  
- **Lab:** logs por etapa (início/fim/erro), `dry-run` para operações destrutivas e mensagens de erro acionáveis.  
- **Produção:** logs estruturados, métricas de execução, rastreabilidade de falhas e padrões de observabilidade (SLO/SLA operacional).

**Sugestão de rubric de correção (0-2)**  
- `0`: execução opaca, sem previsibilidade.  
- `1`: logs básicos sem `dry-run` ou sem padrão.  
- `2`: logs claros por etapa + opção de simulação + erro acionável.

**Exemplo do gap (Grupo 1)**  
```python
# solution_task_1_group_1/provision.py
response = rds.create_db_instance(...)
print("Instância criada")
```

**Exemplo do melhor grupo (Grupo 5)**  
```python
# solution_task_1_group_5/01_instance.py
logger.info("Passo 1/8 - Carregando variáveis de ambiente")
logger.info("Passo 2/8 - Lendo configuração do RDS")
...
logger.info("Passo 8/8 - Provisionamento concluído")
```

**Exemplo ideal (produção)**  
```python
def run_pipeline(cfg, dry_run=False):
    logger.info("pipeline_start", extra={"dry_run": dry_run, "run_id": cfg.run_id})
    if dry_run:
        logger.info("dry_run_plan", extra={"actions": planned_actions(cfg)})
        return 0
    step("provision", lambda: provision(cfg))
    step("load", lambda: load(cfg))
    step("validate", lambda: validate(cfg))
    logger.info("pipeline_success", extra={"run_id": cfg.run_id})
```

---

## Checklist final para futuras entregas da Task 1

- Provisionamento idempotente e reexecutável.
- Segurança de rede restritiva (evitar `0.0.0.0/0`).
- Configuração sem hardcode e com segredos protegidos.
- Carga com transação, tratamento de erro e fechamento correto de recursos.
- Validação com critérios objetivos de aprovação e `exit code`.
- Operabilidade com logs por etapa e, quando possível, `dry-run`.

Se os itens acima forem atendidos, a solução tende a ser corrigível, reproduzível e muito mais próxima de um padrão de engenharia de dados profissional.
