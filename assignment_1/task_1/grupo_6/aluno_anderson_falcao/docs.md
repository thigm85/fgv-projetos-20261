# Guia de Execução: Task 1 - Pipeline ClassicModels (RDS)

Este documento descreve o processo de configuração e execução da Task 1, focada no provisionamento, carga e validação de um banco de dados MySQL no Amazon RDS. 
---

## 1. Configuração de Credenciais (AWS CLI)

Antes de iniciar, garanta que suas credenciais da AWS estejam configuradas. No contexto do **AWS Academy**, lembre-se de que as credenciais são temporárias.

1. No console do AWS Academy, clique em **AWS Details**.
2. Copie o conteúdo de **AWS CLI** (que inclui `aws_access_key_id`, `aws_secret_access_key` e `aws_session_token`).
3. Cole o conteúdo no arquivo `~/.aws/credentials` e salve.
---

## 2. Configuração do Ambiente (.env)

O projeto utiliza um arquivo `.env` para centralizar configurações sensíveis e caminhos de arquivos. Crie um arquivo chamado `.env` na raiz do projeto com o seguinte conteúdo:

```env
USERNAME = "exemplo_usuario"
PASSWORD = "exemplo_senha"
LOCAL_SQL = "..\..\data\mysqlsampledatabase.sql"
```

---

## 3. Instalação de Dependências

Certifique-se de ter o Python instalado. Recomenda-se o uso de um ambiente virtual (`venv`).

```bash
# Instala as bibliotecas necessárias (boto3, mysql-connector-python, python-dotenv)
pip install -r requirements.txt
```

---

## 4. Ordem de Execução dos Scripts

Os scripts devem ser executados sequencialmente para garantir a integridade do provisionamento e da carga.

### Passo 1: Provisionamento da Infraestrutura
```bash
python 1_provision_rds.py
```
- **O que faz:** Cria o Security Group restritivo (apenas seu IP atual), provisiona a instância RDS MySQL (`db.t3.micro`) e aguarda o estado `available`.

### Passo 2: Carga de Dados (ETL Inicial)
```bash
python 2_load_data.py
```
- **O que faz:** Lê o arquivo SQL definido no `.env`, cria o banco de dados `classicmodels` e executa os statements de criação de tabelas e inserção de dados.

### Passo 3: Validação e Quality Gate
```bash
python 3_validate.py
```
- **O que faz:** Verifica a presença de todas as tabelas, realiza a contagem de registros e executa queries de integridade referencial e lógica de negócio.

---

## Melhores Práticas Implementadas

Com base no feedback, as seguintes melhorias foram aplicadas:

- **Segurança de Rede:** O Security Group não utiliza mais `0.0.0.0/0`. Ele detecta automaticamente o IP público da sua máquina e libera apenas o acesso `/32` na porta 3306.
- **Robustez Operacional:** Inclusão de tratamento de erros com rollback e lógica de espera (*waiters*) nativa da AWS.
- **Gestão de Segredos:** Separação total entre código e credenciais via `.env` e validação de variáveis obrigatórias no início da execução.
- **Observabilidade:** Logs por etapa e feedback visual do progresso da carga de dados.
