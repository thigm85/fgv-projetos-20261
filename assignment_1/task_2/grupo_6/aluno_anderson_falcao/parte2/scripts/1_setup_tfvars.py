"""
Gera terraform.tfvars a partir de rds_credentials.json e .env existentes.
Execute antes do 'terraform apply'.
"""

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(os.path.join("..", ".env"))

# --- Configuraçoes ---------------------------------------------------------------
CREDENTIALS_FILE = os.path.join("..", "rds_credentials.json")  # ajuste se necessario
OUTPUT_FILE      = os.path.join("terraform", "terraform.tfvars") # ajuse se necessario
REGION           = "us-east-1"
PROJECT_NAME     = "classicmodels"

GLUE_CONFIG = {
    "glue_worker_type":       "G.1X",
    "glue_number_of_workers": 2,
    "glue_timeout_minutes":   60,
}
# --------------------------------------------------------------------------------


def load_rds_credentials(filepath: str) -> dict:
    """Carrega credenciais RDS do arquivo JSON gerado pelo 1_provision_rds.py."""
    path = Path(filepath)
    if not path.exists():
        # Tenta encontrar na pasta atual também
        alt = Path("rds_credentials.json")
        if alt.exists():
            path = alt
        else:
            sys.exit(
                f"X Arquivo '{filepath}' nao encontrado.\n"
                "  Execute primeiro: python 1_provision_rds.py\n"
                f"  Ou ajuste CREDENTIALS_FILE no topo deste script."
            )
    with open(path) as f:
        return json.load(f)


def validate_env() -> tuple[str, str]:
    """Le USERNAME e PASSWORD do .env com fail-fast."""
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    missing = []
    if not username:
        missing.append("USERNAME")
    if not password:
        missing.append("PASSWORD")
    if missing:
        sys.exit(
            f"X Variaveis de ambiente obrigatorias ausentes: {', '.join(missing)}\n"
            "  Certifique-se de ter um arquivo .env com USERNAME=... e PASSWORD=..."
        )
    return username, password


def generate_tfvars(creds: dict, username: str, password: str) -> str:
    """Monta o conteudo do arquivo terraform.tfvars."""
    lines = [
        "# Gerado automaticamente por 1_setup_tfvars.py",
        "",
        f'region       = "{REGION}"',
        f'project_name = "{PROJECT_NAME}"',
        "",
        "# --- RDS -------------------------------------------------------------",
        f'rds_host = "{creds["host"]}"',
        f'rds_port = {creds["port"]}',
        f'db_name  = "{creds["database"]}"',
        "",
        "# --- Credenciais -----------------------------------------",
        f'db_username = "{username}"',
        f'db_password = "{password}"',
        "",
        "# --- Glue ------------------------------------------------------------",
        f'glue_worker_type       = "{GLUE_CONFIG["glue_worker_type"]}"',
        f'glue_number_of_workers = {GLUE_CONFIG["glue_number_of_workers"]}',
        f'glue_timeout_minutes   = {GLUE_CONFIG["glue_timeout_minutes"]}',
    ]
    return "\n".join(lines) + "\n"


def main():
    print("=" * 55)
    print("  Setup terraform.tfvars - classicmodels lab")
    print("=" * 55)

    print(f"\n[1/3] Carregando credenciais RDS de '{CREDENTIALS_FILE}'...")
    creds = load_rds_credentials(CREDENTIALS_FILE)
    print(f"      Host: {creds['host']}:{creds['port']}")

    print("\n[2/3] Validando variaveis de ambiente (.env)...")
    username, password = validate_env()
    print(f"      USERNAME: {username}")
    print(f"      PASSWORD: ***")

    print(f"\n[3/3] Escrevendo '{OUTPUT_FILE}'...")
    content = generate_tfvars(creds, username, password)
    with open(OUTPUT_FILE, "w") as f:
        f.write(content)

    print(f"\n{'=' * 55}")
    print(f"  OK '{OUTPUT_FILE}' gerado com sucesso!")
    print(f"{'=' * 55}")
    print("\n  Próximos passos:")
    print("    terraform init")
    print("    terraform plan")
    print("    terraform apply")
    print(f"\n    ATENÇAO: '{OUTPUT_FILE}' contem credenciais.")

if __name__ == "__main__":
    main()
