import os
import time
import json
import subprocess
import boto3
from dotenv import load_dotenv

# Carrega variáveis
load_dotenv(dotenv_path="rds_connection.env")

def info(msg):  print(f"[INFO] {msg}")
def error(msg):
    print(f"[ERRO] {msg}")
    raise SystemExit(1)
def step(num, total, msg): print(f"\n[ORQUESTRADOR {num}/{total}] {msg}")

def require_env(keys: list[str]):
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        error(
            "Variáveis ausentes no arquivo rds_connection.env: "
            + ", ".join(missing)
            + "\nDica: rode primeiro provision_rds.py para gerar esse arquivo."
        )

def run_command(cmd, cwd=None) -> str:
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        return result.stdout or ""
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        error(f"Falha ao executar comando: {' '.join(cmd)}")
        raise

def main():
    total_steps = 3
    tf_dir = "terraform"

    require_env([
        "RDS_HOST",
        "RDS_DB",
        "RDS_USER",
        "RDS_PASSWORD",
        "VPC_ID",
        "SUBNET_ID",
        "RDS_SG_ID",
    ])
    
    step(1, total_steps, "Provisionando Infraestrutura de ETL (Terraform)")
    info("Inicializando Terraform...")
    run_command(["terraform", "init"], cwd=tf_dir)
    
    info("Aplicando plano do Terraform...")
    rds_port = os.getenv("RDS_PORT") or "3306"
    tf_vars = [
        "-var", f"db_host={os.getenv('RDS_HOST')}",
        "-var", f"db_port={rds_port}",
        "-var", f"db_name={os.getenv('RDS_DB')}",
        "-var", f"db_user={os.getenv('RDS_USER')}",
        "-var", f"db_password={os.getenv('RDS_PASSWORD')}",
        "-var", f"vpc_id={os.getenv('VPC_ID')}",
        "-var", f"subnet_id={os.getenv('SUBNET_ID')}",
        "-var", f"rds_sg_id={os.getenv('RDS_SG_ID')}",
        "-auto-approve"
    ]
    run_command(["terraform", "apply"] + tf_vars, cwd=tf_dir)
    
    # Captura outputs do Terraform
    outputs_raw = run_command(["terraform", "output", "-json"], cwd=tf_dir)
    outputs = json.loads(outputs_raw)
    job_name = outputs["glue_job_name"]["value"]
    bucket_name = outputs["s3_bucket_name"]["value"]
    info(f"Infra pronta. Job: {job_name} | Bucket: {bucket_name}")

    # Passo 2: Iniciar Glue Job
    step(2, total_steps, f"Iniciando Glue Job: {job_name}")
    glue = boto3.client("glue")
    response = glue.start_job_run(JobName=job_name)
    run_id = response["JobRunId"]
    info(f"Job iniciado. RunId: {run_id}")

    # Passo 3: Monitorar Job
    step(3, total_steps, "Aguardando conclusão do Job (Polling)")
    while True:
        status_resp = glue.get_job_run(JobName=job_name, RunId=run_id)
        status = status_resp["JobRun"]["JobRunState"]
        info(f"Status atual: {status}")
        
        if status in ["SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT"]:
            break
        time.sleep(30)

    if status != "SUCCEEDED":
        error(f"O Job do Glue terminou com erro: {status}")

    print("\n" + "="*50)
    print(" EXECUÇÃO DO ETL CONCLUÍDA COM SUCESSO! ")
    print(f" Bucket S3: {bucket_name} ")
    print("="*50)

if __name__ == "__main__":
    main()
