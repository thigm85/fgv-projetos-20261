# Task 3 — Consultas Athena e dashboard (Grupo 4 / Aluno Luciano)

Implementação da [query.md](../../../query.md) §4: três consultas no Amazon Athena sobre o esquema estrela da Task 2 e dashboard interativo no Jupyter.

## Pré-requisitos

1. **Task 1** concluída: RDS com `classicmodels` — [`task_1/grupo_4/aluno_luciano`](../../../task_1/grupo_4/aluno_luciano/).
2. **Task 2 (ETL)** concluída: Glue Job `SUCCEEDED`, Parquet no S3 e tabelas no Glue Data Catalog — [`../task_2_redo`](../task_2_redo/).
3. Credenciais AWS válidas na sessão local (`aws sts get-caller-identity`).

## Configuração

```bash
cd assignment_1/task_3/grupo_4/aluno_luciano/task_3
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Obtenha o nome do database Glue/Athena (após `terraform apply` e Glue Job na pasta `task_2_redo`):

```bash
cd ../task_2_redo/terraform
terraform output -raw glue_database_name
```

No notebook, defina `GLUE_DATABASE` com esse valor (padrão do Terraform: `classicmodels_star_g4`).

## Execução

```bash
cd assignment_1/task_3/grupo_4/aluno_luciano/task_3
jupyter lab classicmodels_dashboard.ipynb
```

Execute as células em ordem. As seções 4.2–4.4 consultam o Athena; a seção 4.5 monta o dashboard com filtros sobre o DataFrame da 4.4.

### Athena — bucket de resultados

Se as consultas falharem por falta de local de resultados, defina no notebook (ou via variável de ambiente) um bucket S3 onde a conta pode gravar resultados do Athena, por exemplo:

```python
import awswrangler as wr
wr.config.athena_query_results_bucket = "s3://SEU-BUCKET-DE-RESULTADOS/athena/"
```

No ambiente de lab, o workgroup `primary` costuma já apontar para um bucket válido.

## Critérios de conclusão (enunciado)

1. Três consultas Athena bem-sucedidas: `dim_products` (4.2), vendas por país (4.3), detalhamento (4.4).
2. Dashboard com intervalo de datas, país, linha de produto, Top N e gráfico de barras coerente com os filtros.
3. Apenas esquema estrela da Task 2 — sem SQL contra o RDS da Task 1.


![example_image](./example_image.png)