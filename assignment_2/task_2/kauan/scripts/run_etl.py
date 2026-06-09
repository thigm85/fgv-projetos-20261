import os
import time
import json
import subprocess
import boto3
from dotenv import load_dotenv

# Define diretórios base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Como o script foi movido para scripts/, a raiz da tarefa é o diretório pai
TASK_ROOT = os.path.dirname(BASE_DIR)
TF_DIR = os.path.join(TASK_ROOT, "terraform")
ENV_PATH = os.path.join(TASK_ROOT, "rds_connection.env")

# Carrega variáveis
load_dotenv(dotenv_path=ENV_PATH)

def info(msg):  print(f"[INFO] {msg}")
def error(msg):
    print(f"[ERRO] {msg}")
    raise SystemExit(1)
def step(num, total, msg): print(f"\n[ORQUESTRADOR {num}/{total}] {msg}")

def require_env(keys: list[str]):
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        error(
            f"Variáveis ausentes no arquivo {ENV_PATH}: "
            + ", ".join(missing)
            + "\nDica: rode primeiro provision_rds.py para gerar esse arquivo."
        )

def run_command(cmd, cwd=None) -> str:
    try:
        # Tenta encontrar o executável se ele não estiver no PATH completo
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        return result.stdout or ""
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        error(f"Falha ao executar comando: {' '.join(cmd)}")
    except FileNotFoundError as e:
        error(f"Erro: {e}. Certifique-se de que o comando '{cmd[0]}' está instalado e que o diretório '{cwd}' existe.")
        raise

def main():
    total_steps = 4

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
    info(f"Usando diretório Terraform: {TF_DIR}")
    info("Inicializando Terraform...")
    run_command(["terraform", "init"], cwd=TF_DIR)
    
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
    run_command(["terraform", "apply"] + tf_vars, cwd=TF_DIR)
    
    # Captura outputs do Terraform
    outputs_raw = run_command(["terraform", "output", "-json"], cwd=TF_DIR)
    outputs = json.loads(outputs_raw)
    job_name = outputs["glue_job_name"]["value"]
    bucket_name = outputs["s3_bucket_name"]["value"]
    crawler_name = outputs["glue_crawler_name"]["value"]
    db_gold = outputs["glue_database_name"]["value"]
    athena_wg = outputs["athena_workgroup"]["value"]
    info(f"Infra pronta. Job: {job_name} | Bucket: {bucket_name} | Crawler: {crawler_name} | DB: {db_gold} | WG: {athena_wg}")

    # Atualiza rds_connection.env com os nomes dinâmicos
    with open(ENV_PATH, "a") as f:
        f.write(f"GLUE_DATABASE_NAME={db_gold}\n")
        f.write(f"ATHENA_WORKGROUP_NAME={athena_wg}\n")
    info(f"Variáveis GLUE_DATABASE_NAME e ATHENA_WORKGROUP_NAME salvas em {ENV_PATH}")

    # Passo 2: Iniciar Glue Job
    step(2, total_steps, f"Iniciando Glue Job: {job_name}")
    glue = boto3.client("glue")
    rds_port = os.getenv("RDS_PORT") or "3306"
    response = glue.start_job_run(
        JobName=job_name,
        Arguments={
            "--db_host": os.getenv("RDS_HOST"),
            "--db_port": rds_port,
            "--db_user": os.getenv("RDS_USER"),
            "--db_password": os.getenv("RDS_PASSWORD"),
        }
    )
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

    # Passo 4: Executar Crawler
    step(4, total_steps, f"Iniciando Glue Crawler: {crawler_name}")
    glue.start_crawler(Name=crawler_name)
    info("Crawler iniciado. Aguardando finalização...")
    
    while True:
        crawler_resp = glue.get_crawler(Name=crawler_name)
        status = crawler_resp["Crawler"]["State"]
        info(f"Status do Crawler: {status}")
        
        if status == "READY":
            break
        time.sleep(30)

    print("\n" + "="*50)
    print(" EXECUÇÃO DO ETL E CRAWLER CONCLUÍDA COM SUCESSO! ")
    print(f" Bucket S3: {bucket_name} ")
    print(f" Banco de Dados Glue: {db_gold} ")
    print("="*50)

if __name__ == "__main__":
    main()
