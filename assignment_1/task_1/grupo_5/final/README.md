# Grupo 5 - Final

Esta pasta consolida a solucao final do grupo.

## Escopo
- Provisionamento e carga do banco MySQL no RDS.
- Provisionamento de infraestrutura Glue/S3 via Terraform.
- Execucao do job ETL no Glue.
- Execucao do crawler para catalogacao no Glue Data Catalog.

## Execucao
Da raiz do repositorio:

```bash
cp assignment_1/task_3/grupo_5/antonio/.env.example assignment_1/task_3/grupo_5/antonio/.env
source .venv/bin/activate
assignment_1/task_3/grupo_5/antonio/run_task3_pipeline.sh
```

## Artefatos principais
- Pipeline: `assignment_1/task_3/grupo_5/antonio/run_task3_pipeline.sh`
- ETL Glue: `assignment_1/task_3/grupo_5/antonio/glue/etl_job.py`
- Terraform: `assignment_1/task_3/grupo_5/antonio/terraform/`
