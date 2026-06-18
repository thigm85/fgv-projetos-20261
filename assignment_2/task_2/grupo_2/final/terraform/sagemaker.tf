# ==========================================================================
# SageMaker Notebook Instance — dashboard interativo (Task 3)
#
# Uso:
#   terraform apply -target=aws_sagemaker_notebook_instance.dashboard
#   (ou simplesmente `terraform apply` — sobe junto com o resto)
#
# Como abrir / parar: ver terraform/DASHBOARD.md
# ==========================================================================

# Upload do notebook local para o S3 (Task 3 abre a partir daí no on-create).
resource "aws_s3_object" "dashboard_notebook" {
  bucket = aws_s3_bucket.data.id
  key    = "notebooks/dashboard.ipynb"
  source = "${path.module}/../notebook/dashboard.ipynb"
  etag   = filemd5("${path.module}/../notebook/dashboard.ipynb")
}

# ---------------------------------------------------------------------------
# Lifecycle Configuration
#   on_create: instala deps Python + baixa notebook do S3 + gera .env
#   on_start : sobe daemon de auto-stop por idle (1h sem uso → stop)
# ---------------------------------------------------------------------------
resource "aws_sagemaker_notebook_instance_lifecycle_configuration" "dashboard" {
  name = "classicmodels-dashboard-lcc"

  on_create = base64encode(<<-EOT
    #!/bin/bash
    set -e
    sudo -u ec2-user -i <<'INNER'
    set -e
    cd /home/ec2-user/SageMaker
    mkdir -p classicmodels/notebook classicmodels/src

    # Baixa notebook (uploaded via terraform).
    aws s3 cp s3://${aws_s3_bucket.data.bucket}/notebooks/dashboard.ipynb classicmodels/notebook/dashboard.ipynb

    # Grava .env consumido pelo notebook (mesmas vars que local_file.env local).
    cat > classicmodels/src/.env <<EOF
    GLUE_DATABASE=${aws_glue_catalog_database.analytics.name}
    ATHENA_WORKGROUP=${aws_athena_workgroup.lab.name}
    ATHENA_OUTPUT_LOCATION=s3://${aws_s3_bucket.athena_results.bucket}/results/
    IN_SAGEMAKER=1
    EOF

    # Instala deps no kernel python3 (conda_python3 — o default ao abrir notebook).
    source /home/ec2-user/anaconda3/bin/activate python3
    pip install --quiet awswrangler ipywidgets seaborn
    source /home/ec2-user/anaconda3/bin/deactivate
    INNER
  EOT
  )

  on_start = base64encode(<<-EOT
    #!/bin/bash
    set -e
    IDLE_TIME=3600  # 1h sem atividade → stop

    # Script oficial AWS (aws-samples/amazon-sagemaker-notebook-instance-lifecycle-config-samples)
    cat > /home/ec2-user/auto-stop-idle.py <<'PYEOF'
    import boto3, requests, time, os
    from datetime import datetime
    IDLE = int(os.environ.get("IDLE_TIME", 3600))
    NAME = os.environ["NB_NAME"]
    REGION = os.environ["AWS_REGION"]
    def is_idle():
        r = requests.get("http://localhost:8443/api/sessions").json()
        if not r: return True
        for s in r:
            last = s["kernel"]["last_activity"].replace("Z", "+00:00")
            delta = (datetime.now(tz=datetime.fromisoformat(last).tzinfo) - datetime.fromisoformat(last)).total_seconds()
            if delta < IDLE: return False
        return True
    if is_idle():
        boto3.client("sagemaker", region_name=REGION).stop_notebook_instance(NotebookInstanceName=NAME)
    PYEOF

    # Cron a cada 5 min
    NB_NAME=$(jq -r .ResourceName /opt/ml/metadata/resource-metadata.json)
    REGION=$(curl -s http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region)
    (crontab -l 2>/dev/null; echo "*/5 * * * * IDLE_TIME=$IDLE_TIME NB_NAME=$NB_NAME AWS_REGION=$REGION /home/ec2-user/anaconda3/bin/python /home/ec2-user/auto-stop-idle.py") | crontab -
  EOT
  )
}

# ---------------------------------------------------------------------------
# Notebook Instance
# ---------------------------------------------------------------------------
resource "aws_sagemaker_notebook_instance" "dashboard" {
  name                  = "classicmodels-dashboard"
  role_arn              = local.glue_role_arn  # LabRole — já tem Athena, S3, Glue, Secrets
  instance_type         = "ml.t3.medium"
  volume_size           = 5
  lifecycle_config_name = aws_sagemaker_notebook_instance_lifecycle_configuration.dashboard.name

  depends_on = [aws_s3_object.dashboard_notebook]
}

output "sagemaker_notebook_name" {
  value       = aws_sagemaker_notebook_instance.dashboard.name
  description = "Nome da Notebook Instance — usar nos comandos aws sagemaker"
}
