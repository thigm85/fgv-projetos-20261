import sys
import os
import logging
import argparse
import boto3
import time
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("UploadNotebook")

def enviar_notebook_s3(caminho_ficheiro, nome_bucket, regiao):
    logger.info("Passo 1/4 - Iniciando sessão com a AWS e a prepararando o upload")
    
    s3_client = boto3.client("s3", region_name=regiao)
    nome_destino_s3 = "notebooks/dashboard.ipynb"
    
    try:
        logger.info(f"Enviando o arquivo {caminho_ficheiro} para o armazenamento em nuvem s3://{nome_bucket}/{nome_destino_s3}")
        s3_client.upload_file(caminho_ficheiro, nome_bucket, nome_destino_s3)
        logger.info("Passo 2/4 - Upload concluído com sucesso para o Amazon S3!")
    except ClientError as erro:
        logger.error(f"Erro ao enviar o arquivo para o S3: {erro}")
        sys.exit(1)

def reiniciar_sagemaker(nome_instancia, regiao):
    logger.info(f"Passo 3/4 - Reiniciando instancia SageMaker: {nome_instancia}")
    sagemaker_client = boto3.client("sagemaker", region_name=regiao)
    
    try:
        status = sagemaker_client.describe_notebook_instance(NotebookInstanceName=nome_instancia)["NotebookInstanceStatus"]
        
        if status == "InService":
            logger.info("Parando a instancia... (isso pode levar alguns minutos)")
            sagemaker_client.stop_notebook_instance(NotebookInstanceName=nome_instancia)
            while status != "Stopped":
                time.sleep(15)
                status = sagemaker_client.describe_notebook_instance(NotebookInstanceName=nome_instancia)["NotebookInstanceStatus"]
        
        if status == "Stopped":
            logger.info("Iniciando a instância novamente. A configuração da infraestrutura garante que o notebook será baixado automaticamente do S3...")
            sagemaker_client.start_notebook_instance(NotebookInstanceName=nome_instancia)
            logger.info("O comando para iniciar a instância foi enviado para a AWS...")
        else:
            logger.warning(f"A instancia esta num estado inesperado: {status}. Nao foi possivel reiniciar.")
            
    except ClientError as erro:
        logger.error(f"Erro ao interagir com o SageMaker: {erro}")
        sys.exit(1)

def obter_link_acesso(nome_instancia, regiao):
    logger.info("Passo 4/4 - Aguardando a instancia ficar pronta para gerar o link do notebook (isso pode levar alguns minutos)...")
    sagemaker_client = boto3.client("sagemaker", region_name=regiao)
    
    status = ""
    while status != "InService":
        status = sagemaker_client.describe_notebook_instance(NotebookInstanceName=nome_instancia)["NotebookInstanceStatus"]
        if status != "InService":
            time.sleep(15)
            
    resposta = sagemaker_client.create_presigned_notebook_instance_url(NotebookInstanceName=nome_instancia)
    
    print("\nO ambiente esta pronto! Clique no link abaixo para abrir o Jupyter:")
    print(resposta["AuthorizedUrl"])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Faz o upload do notebook para o S3.")
    parser.add_argument("--bucket_name", required=True, help="Nome do bucket do S3")
    parser.add_argument("--sagemaker-name", required=False, default="classicmodels-dashboard", help="Nome da instancia do SageMaker")
    parser.add_argument("--aws-region", required=False, default="us-east-1", help="Regiao da AWS")
    args = parser.parse_args()

    notebook_local = "dashboard.ipynb"
    
    if not os.path.exists(notebook_local):
        logger.error(f"O arquivo de notebook {notebook_local} não foi encontrado no diretório atual.")
        sys.exit(1)
        
    enviar_notebook_s3(notebook_local, args.bucket_name, args.aws_region)
    reiniciar_sagemaker(args.sagemaker_name, args.aws_region)
    obter_link_acesso(args.sagemaker_name, args.aws_region)
