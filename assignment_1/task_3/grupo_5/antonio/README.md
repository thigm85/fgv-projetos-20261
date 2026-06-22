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

What the pipeline does:
- Provisions/reuses RDS and loads `classicmodels`.
- Provisions Glue/S3 infrastructure with Terraform.
- Runs Glue ETL job and waits for `SUCCEEDED`.
- Runs Glue Crawler and waits for `SUCCEEDED`.

Optional:
- `RUN_CRAWLER=false` to skip crawler execution.
- `LOAD_SOURCE_DATA=false` to skip MySQL reload step.
- `AUTO_INSTALL_DEPS=false` to skip pip auto-install.
- `GLUE_TIMEOUT_SECONDS=5400` to increase Glue wait timeout.
- `CRAWLER_TIMEOUT_SECONDS=3600` to increase crawler wait timeout.

After it finishes, register the Jupyter kernel and open the notebook:

```bash
python -m ipykernel install --user --name fgv-task3 --display-name "FGV Task 3"
cd assignment_1/task_3/grupo_5/antonio
jupyter lab
```

Open `task3_dashboard.ipynb`, select kernel `FGV Task 3`, and run all cells.

Local files that should not be committed are ignored by the repository `.gitignore`.
