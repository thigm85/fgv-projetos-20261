# Dashboard SageMaker — como usar

Notebook `dashboard.ipynb` rodando em SageMaker Notebook Instance.

## O que o Terraform cria (`sagemaker.tf`)

| Recurso | Função |
|---|---|
| `aws_s3_object.dashboard_notebook` | Upload do `notebook/dashboard.ipynb` local para `s3://<bucket>/notebooks/`. |
| `aws_sagemaker_notebook_instance_lifecycle_configuration.dashboard` | Scripts bash. **`on_create`**: instala `awswrangler/ipywidgets/seaborn`, baixa notebook do S3, gera `src/.env`. **`on_start`**: registra cron de auto-stop por idle (1h). |
| `aws_sagemaker_notebook_instance.dashboard` | EC2 `ml.t3.medium` com JupyterLab. Role = `LabRole` (já tem permissões Athena/S3/Glue). |

Estado padrão após `terraform apply`: instance criada e **`InService` (rodando)**. Já cobra. Parar logo se não for usar agora.

## Comandos do dia a dia

Nome da instance: `classicmodels-dashboard` (output do Terraform).

### Abrir
```bash
# Ligar (se estiver parada — leva ~2 min)
aws sagemaker start-notebook-instance --notebook-instance-name classicmodels-dashboard

# Esperar ficar InService
aws sagemaker wait notebook-instance-in-service --notebook-instance-name classicmodels-dashboard

# Gerar URL e abrir direto no notebook
URL=$(aws sagemaker create-presigned-notebook-instance-url \
  --notebook-instance-name classicmodels-dashboard \
  --query AuthorizedUrl --output text)
# URL vem como https://...sagemaker.aws?authToken=...
# Insere /lab/tree/<path> antes do ?authToken=
NB_URL=$(echo "$URL" | sed 's|sagemaker\.aws?|sagemaker.aws/lab/tree/classicmodels/notebook/dashboard.ipynb?|')
open "$NB_URL"
```

Notebook está em `SageMaker/classicmodels/notebook/dashboard.ipynb`.

### Kernel

Selecionar **`conda_python3`** ao abrir. É o env onde o LCC instalou `awswrangler`,
`ipywidgets`, `seaborn`. Outros kernels (pytorch, tensorflow) não têm as libs.

### Parar (manual)
```bash
aws sagemaker stop-notebook-instance --notebook-instance-name classicmodels-dashboard
```

### Status
```bash
aws sagemaker describe-notebook-instance \
  --notebook-instance-name classicmodels-dashboard \
  --query NotebookInstanceStatus
```
Estados: `Pending` → `InService` → `Stopping` → `Stopped`.

## Auto-stop por idle

Cron interno checa a cada 5 min se algum kernel está rodando. **1h sem atividade → `stop-notebook-instance` automático.**

Configurado em `on_start` do LCC, ativa toda vez que liga. Não precisa fazer nada.

Trocar timeout: editar `IDLE_TIME=3600` em `sagemaker.tf` (segundos) e reaplicar.

## Atualizar o notebook

Editou `notebook/dashboard.ipynb` local? Re-upload:

```bash
cd terraform && terraform apply  # detecta filemd5 mudado, faz upload
```

Mas **a instance não baixa de novo automaticamente** — `on_create` só roda 1x. Pra puxar versão nova:

```bash
# Dentro do JupyterLab terminal:
aws s3 cp s3://<bucket>/notebooks/dashboard.ipynb /home/ec2-user/SageMaker/classicmodels/notebook/dashboard.ipynb
```

Ou destruir + recriar a notebook instance:
```bash
terraform taint aws_sagemaker_notebook_instance.dashboard
terraform apply
```
