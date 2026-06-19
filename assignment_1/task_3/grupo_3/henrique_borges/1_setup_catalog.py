"""
1_setup_catalog.py — Provisiona o catálogo Glue e executa o crawler do star schema.

Responsabilidades
-----------------
1. Valida variáveis de ambiente obrigatórias (.env).
2. Gera terraform.tfvars a partir das credenciais do .env.
3. Executa ``terraform init`` + ``terraform apply`` para criar:
   - Glue Catalog Database  (classicmodels_analytics)
   - Glue Crawler           (classicmodels-star-schema-crawler)
4. Inicia o crawler e aguarda conclusão com status SUCCEEDED.
5. Exibe o resumo do catálogo provisionado (database + S3 de saída Athena).

Pré-requisitos
--------------
- Terraform >= 1.0 instalado e no PATH.
- Bucket S3 do data lake já existente (criado pela Task 2).
- Arquivo .env com as variáveis listadas em REQUIRED_VARS.

Uso
---
    cd assignment_1/task_3/grupo_3/henrique_borges
    python 1_setup_catalog.py

Saída
-----
- terraform.tfvars   — gerado automaticamente; gitignored (contém credenciais).
- catalog_info.json  — gerado pelo Terraform output; lido pelo notebook e por
                       2_validate_athena.py.

Exit codes
----------
- 0  Provisionamento e crawler concluídos com sucesso.
- 1  Variável ausente, falha no Terraform ou timeout/erro do crawler.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

# Variáveis exigidas antes de qualquer operação
REQUIRED_VARS = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "S3_BUCKET_NAME",
]

CRAWLER_POLL_INTERVAL = 15   # segundos entre cada verificação de estado
CRAWLER_MAX_ATTEMPTS  = 40   # timeout total: 40 × 15 s = 10 min


def check_env() -> None:
    """Verifica que todas as variáveis obrigatórias estão definidas no .env.

    Encerra o processo com exit code 1 se alguma estiver ausente, listando
    todas as variáveis faltantes de uma só vez para facilitar o diagnóstico.
    """
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print(f"[ERRO] Variáveis ausentes no .env: {', '.join(missing)}")
        sys.exit(1)


def generate_tfvars() -> None:
    """Gera terraform.tfvars a partir das credenciais carregadas do .env.

    O arquivo é listado no .gitignore e nunca deve ser commitado, pois contém
    a chave secreta e o session token da sessão AWS Lab.
    """
    content = (
        f'aws_access_key_id     = "{os.getenv("AWS_ACCESS_KEY_ID")}"\n'
        f'aws_secret_access_key = "{os.getenv("AWS_SECRET_ACCESS_KEY")}"\n'
        f'aws_session_token     = "{os.getenv("AWS_SESSION_TOKEN")}"\n'
        f'aws_region            = "{os.getenv("AWS_REGION", "us-east-1")}"\n'
        f's3_bucket_name        = "{os.getenv("S3_BUCKET_NAME")}"\n'
    )
    (HERE / "terraform.tfvars").write_text(content)
    print("[OK] terraform.tfvars gerado.")


def run_terraform() -> None:
    """Executa ``terraform init`` e ``terraform apply -auto-approve``.

    Cada passo é executado no diretório do módulo (HERE). Falhas de qualquer
    subprocesso encerram o script com exit code 1.
    """
    for step in [["terraform", "init"], ["terraform", "apply", "-auto-approve"]]:
        label = " ".join(step)
        print(f"\n=== {label} ===")
        result = subprocess.run(step, cwd=HERE)
        if result.returncode != 0:
            print(f"[ERRO] Falha: {label}")
            sys.exit(1)


def wait_for_crawler(glue_client, crawler_name: str) -> None:
    """Inicia o Glue Crawler e aguarda até que conclua com status SUCCEEDED.

    O fluxo tem dois loops de polling:
    1. Aguarda o crawler estar em estado READY (caso uma execução anterior
       ainda esteja em andamento).
    2. Inicia o crawler e aguarda retornar ao estado READY após a execução.

    Após o segundo loop, valida ``LastCrawl.Status == SUCCEEDED``.

    Parameters
    ----------
    glue_client:
        Cliente boto3 do AWS Glue já autenticado.
    crawler_name:
        Nome do crawler conforme registrado no Glue Catalog.

    Raises
    ------
    SystemExit(1):
        Timeout atingido ou crawler finalizado com status diferente de SUCCEEDED.
    """
    print(f"\nAguardando crawler '{crawler_name}'...")

    # Fase 1 — garante que o crawler não está rodando antes de disparar
    for attempt in range(1, CRAWLER_MAX_ATTEMPTS + 1):
        state = glue_client.get_crawler(Name=crawler_name)["Crawler"]["State"]
        if state == "READY":
            break
        print(f"  [{attempt}/{CRAWLER_MAX_ATTEMPTS}] Estado atual: {state} — aguardando READY...")
        if attempt == CRAWLER_MAX_ATTEMPTS:
            print("[ERRO] Timeout: crawler não ficou READY antes de iniciar.")
            sys.exit(1)
        time.sleep(CRAWLER_POLL_INTERVAL)

    glue_client.start_crawler(Name=crawler_name)
    print("  Crawler iniciado.")

    # Fase 2 — aguarda a execução concluir
    for attempt in range(1, CRAWLER_MAX_ATTEMPTS + 1):
        state = glue_client.get_crawler(Name=crawler_name)["Crawler"]["State"]
        print(f"  [{attempt}/{CRAWLER_MAX_ATTEMPTS}] Estado: {state}")
        if state == "READY":
            break
        if attempt == CRAWLER_MAX_ATTEMPTS:
            print("[ERRO] Timeout: crawler não concluiu dentro do prazo esperado.")
            sys.exit(1)
        time.sleep(CRAWLER_POLL_INTERVAL)

    last_crawl = glue_client.get_crawler(Name=crawler_name)["Crawler"].get("LastCrawl", {})
    status = last_crawl.get("Status", "DESCONHECIDO")
    if status != "SUCCEEDED":
        print(f"[ERRO] Crawler terminou com status: {status}")
        print(f"       Mensagem: {last_crawl.get('ErrorMessage', '')}")
        sys.exit(1)
    print(f"[OK] Crawler concluído com status: {status}")


def main() -> None:
    """Orquestra as etapas de provisionamento do catálogo Glue.

    Ordem de execução:
    1. check_env      — falha rápido se o ambiente está incompleto.
    2. generate_tfvars — materializa credenciais para o Terraform.
    3. run_terraform   — cria Glue Database e Crawler via IaC.
    4. wait_for_crawler — dispara e monitora o crawler até SUCCEEDED.
    """
    check_env()
    generate_tfvars()
    run_terraform()

    import boto3

    info = json.loads((HERE / "catalog_info.json").read_text())

    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )

    wait_for_crawler(session.client("glue"), info["crawler_name"])

    print("\n" + "=" * 50)
    print("Catálogo configurado com sucesso!")
    print(f"  Database Glue : {info['glue_database']}")
    print(f"  Saída Athena  : {info['athena_output']}")
    print("=" * 50)
    print("\nPróximo passo: python 2_validate_athena.py")


if __name__ == "__main__":
    main()
