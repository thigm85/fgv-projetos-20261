# Run Task 3

From the repository root:

```bash
cp assignment_1/task_3/grupo_5/antonio/.env.example assignment_1/task_3/grupo_5/antonio/.env
```

Fill `.env` with your AWS Academy credentials and `DB_PASSWORD`.

Activate your repo virtual environment and run the pipeline:

```bash
source .venv/bin/activate
assignment_1/task_3/grupo_5/antonio/run_task3_pipeline.sh
```

What the unified pipeline now does:
- Provisions/reuses RDS and loads `classicmodels` (task 1 approach).
- Provisions Glue/S3 infra and runs Glue ETL job (task 3 from group 5).
- Runs Glue Crawler to register curated tables in Glue Catalog/Athena (task 3 from group 1).

Optional:
- Set `RUN_CRAWLER=false` to skip crawler execution.

After it finishes, register the Jupyter kernel and open the notebook:

```bash
python -m ipykernel install --user --name fgv-task3 --display-name "FGV Task 3"
cd assignment_1/task_3/grupo_5/antonio
jupyter lab
```

Open `task3_dashboard.ipynb`, select kernel `FGV Task 3`, and run all cells.

Local files that should not be committed are already ignored: `.env`, `.rds.generated.env`, `.venv/`, Terraform state, `terraform.tfvars`, and `terraform/outputs.json`.
