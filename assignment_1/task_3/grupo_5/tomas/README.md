# Run Task 3

From the repository root:

```bash
cp assignment_1/task_3/grupo_5/tomas/.env.example assignment_1/task_3/grupo_5/tomas/.env
```

Fill `.env` with your AWS Academy credentials and `DB_PASSWORD`.

Activate your repo virtual environment and run the pipeline:

```bash
source .venv/bin/activate
assignment_1/task_3/grupo_5/tomas/run_task3_pipeline.sh
```

After it finishes, register the Jupyter kernel and open the notebook:

```bash
python -m ipykernel install --user --name fgv-task3 --display-name "FGV Task 3"
cd assignment_1/task_3/grupo_5/tomas
jupyter lab
```

Open `task3_dashboard.ipynb`, select kernel `FGV Task 3`, and run all cells.

Local files that should not be committed are already ignored: `.env`, `.rds.generated.env`, `.venv/`, Terraform state, `terraform.tfvars`, and `terraform/outputs.json`.
