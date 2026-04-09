# Task 1 - Solucao de Referencia (RDS)

Este diretorio `assignment_1/solution_task_1/` contem uma referencia executavel para a Task 1 (`assignment_1/task_1/rds.md`), cobrindo provisionamento, carga e validacao do banco de origem no Amazon RDS.

## Estrutura

```text
solution_task_1/
├── .env.example
├── data/
│   └── mysqlsampledatabase.sql
├── lecture_notes.md
├── requirements.txt
├── scripts/
│   ├── load_data.py
│   ├── provision_rds.py
│   └── validate.py
└── task_1_rds_solution.ipynb
```

## Pre-requisitos

- Python 3.10+
- AWS credentials configuradas localmente (via AWS CLI profile ou variaveis de ambiente)
- Cliente `mysql` instalado localmente
- No macOS com Homebrew: `brew install mysql-client` e exportar `PATH="/opt/homebrew/opt/mysql-client/bin:$PATH"` (Apple Silicon)

## Setup

```bash
cd assignment_1/solution_task_1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Preencha o `.env` com credenciais e parametros do seu ambiente.
Se `RDS_ENGINE_VERSION` nao estiver disponivel na regiao escolhida, o script de provisionamento aplica fallback automatico para a versao MySQL mais recente suportada pelo RDS.
O `provision_rds.py --wait` tambem garante regra de ingress no Security Group (tcp/3306). Use `RDS_INGRESS_CIDR` para fixar o bloco permitido; se vazio, o script detecta seu IP publico atual e aplica `/32`.

## Execucao recomendada

```bash
python scripts/provision_rds.py --wait
python scripts/load_data.py
python scripts/validate.py
```

Para simular sem efeitos colaterais:

```bash
python scripts/provision_rds.py --dry-run
python scripts/load_data.py --dry-run
python scripts/validate.py --dry-run
```

## Notebook de estudo

O notebook `task_1_rds_solution.ipynb` explica o fluxo em PT-BR e mostra o codigo dos scripts lendo direto dos arquivos para manter uma unica fonte de verdade.

Dependencias opcionais para executar o notebook sem inflar instalacoes CLI-only:

```bash
pip install jupyter ipykernel
python -m ipykernel install --user --name fgv-rds-task1
```
