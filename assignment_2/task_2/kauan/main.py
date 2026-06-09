#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess

# Obtém o interpretador python atual para garantir execução no mesmo ambiente virtual (.venv)
PYTHON_EXE = sys.executable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def info(msg): print(f"\n\033[1;34m[MAIN INFO]\033[0m {msg}")
def success(msg): print(f"\033[1;32m[SUCESSO]\033[0m {msg}")
def error(msg):
    print(f"\033[1;31m[ERRO]\033[0m {msg}", file=sys.stderr)
    sys.exit(1)

def run_script(script_path: str, args: list = None, env_override: dict = None) -> bool:
    full_path = os.path.join(BASE_DIR, script_path)
    cmd = [PYTHON_EXE, full_path]
    if args:
        cmd.extend(args)
    
    current_env = os.environ.copy()
    if env_override:
        current_env.update(env_override)

    print(f"\n\033[1;33mExecuting: {' '.join(cmd)}\033[0m")
    print("=" * 60)
    
    result = subprocess.run(cmd, env=current_env, cwd=BASE_DIR)
    
    print("=" * 60)
    if result.returncode == 0:
        return True
    else:
        error(f"O script {script_path} falhou com código de saída {result.returncode}.")
        return False

def run_provision():
    info("Executando Provisionamento RDS (scripts/provision_rds.py)...")
    run_script("scripts/provision_rds.py")
    success("RDS provisionado e rds_connection.env atualizado.")

def run_load_data():
    info("Executando Carga Histórica de Dados (scripts/load_data.py)...")
    # Resolve o caminho do dump SQL do Assignment 1 de forma robusta
    sql_file = os.path.normpath(
        os.path.join(BASE_DIR, "..", "..", "..", "assignment_1", "task_1", "data", "mysqlsampledatabase.sql")
    )
    if not os.path.exists(sql_file):
        error(f"Arquivo SQL de carga original não encontrado em: {sql_file}")
    
    run_script("scripts/load_data.py", env_override={"SQL_FILE": sql_file})
    success("Carga inicial e schema do classicmodels criados com sucesso.")

def run_init_watermark(reset: bool = False):
    info("Inicializando Metadados de Watermark (scripts/init_watermark.py)...")
    args = ["--reset"] if reset else []
    run_script("scripts/init_watermark.py", args=args)
    success("Tabela etl_watermark criada e inicializada com o baseline.")

def run_validate_source():
    info("Validando Origem Incremental (validation/validate_incremental_source.py)...")
    run_script("validation/validate_incremental_source.py")
    success("Validação da origem concluída.")

def run_simulate_orders(count: int, seed: int = None):
    info(f"Simulando novos pedidos ({count} pedidos) (scripts/simulate_new_orders.py)...")
    args = ["--count", str(count)]
    if seed is not None:
        args.extend(["--seed", str(seed)])
    run_script("scripts/simulate_new_orders.py", args=args)
    success("Simulação de pedidos novos finalizada.")

def run_etl():
    info("Executando Orquestrador do ETL (scripts/run_etl.py)...")
    run_script("scripts/run_etl.py")
    success("Execução do ETL e Crawler concluída.")

def run_validate_etl():
    info("Validando Dados do ETL no S3 (validation/validate_etl.py)...")
    run_script("validation/validate_etl.py")
    success("Validação do ETL concluída.")

def run_validate_athena():
    info("Validando Consultas no Athena (validation/validate_athena.py)...")
    run_script("validation/validate_athena.py")
    success("Validação do Athena concluída.")

def run_full_flow(count: int, seed: int = None):
    info("=== INICIANDO FLUXO COMPLETO DO PIPELINE (TASK 2) ===")
    
    # 1. Provisiona/Verifica RDS
    run_provision()
    
    # 2. Reseta a base de dados com a carga histórica limpa do Assignment 1
    run_load_data()
    
    # 3. Inicializa o watermark com o MAX(orderDate) da carga histórica
    run_init_watermark()
    
    # 4. Primeira Validação: origem deve estar coerente e sem dados novos/pendentes
    info("Executando primeira validação (BASELINE limpo)...")
    run_validate_source()
    
    # 5. Insere novos pedidos simulados posteriores ao watermark
    run_simulate_orders(count, seed)
    
    # 6. Segunda Validação: origem deve detectar dados pendentes para o ETL e validar integridade dos novos registros
    info("Executando segunda validação (Dados incrementais pendentes)...")
    run_validate_source()
    
    # 7. Executa o ETL incremental via Terraform e AWS Glue
    run_etl()
    
    # 8. Valida os arquivos gerados no S3 (Data Quality)
    run_validate_etl()
    
    # 9. Valida o acesso e partição das tabelas no Athena
    run_validate_athena()
    
    print("\n" + "=" * 60)
    success("FLUXO COMPLETO DO PIPELINE EXECUTADO COM SUCESSO!")
    print("O pipeline incremental está validado de ponta a ponta.")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(
        description="Orquestrador central do Pipeline da Task 2 - ETL incremental, partições e agendamento."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--flow", action="store_true", help="Executa o fluxo completo do pipeline (padrão)")
    group.add_argument("--provision", action="store_true", help="Apenas provisiona/verifica o RDS")
    group.add_argument("--load-data", action="store_true", help="Apenas faz a carga limpa histórica no MySQL")
    group.add_argument("--init-watermark", action="store_true", help="Apenas inicializa a tabela de watermark")
    group.add_argument("--reset-watermark", action="store_true", help="Força o reset do watermark para o baseline histórico")
    group.add_argument("--validate", action="store_true", help="Apenas roda o script de validação de origem")
    group.add_argument("--simulate", action="store_true", help="Apenas executa a simulação de novos pedidos")
    group.add_argument("--run-etl", action="store_true", help="Executa o orquestrador do ETL (Terraform + Glue + Crawler)")
    group.add_argument("--validate-etl", action="store_true", help="Valida os dados resultantes do ETL no S3")
    group.add_argument("--validate-athena", action="store_true", help="Valida o catálogo Glue através do Athena")

    parser.add_argument("--count", type=int, default=5, help="Quantidade de pedidos a simular (default: 5)")
    parser.add_argument("--seed", type=int, default=None, help="Semente de aleatoriedade para simulação")
    
    args = parser.parse_args()

    # Define comportamento padrão: se nenhuma flag de ação for especificada, roda o fluxo completo (--flow)
    if not (args.provision or args.load_data or args.init_watermark or args.reset_watermark or 
            args.validate or args.simulate or args.run_etl or args.validate_etl or args.validate_athena):
        args.flow = True

    if args.provision:
        run_provision()
    elif args.load_data:
        run_load_data()
    elif args.init_watermark:
        run_init_watermark(reset=False)
    elif args.reset_watermark:
        run_init_watermark(reset=True)
    elif args.validate:
        run_validate_source()
    elif args.simulate:
        run_simulate_orders(args.count, args.seed)
    elif args.run_etl:
        run_etl()
    elif args.validate_etl:
        run_validate_etl()
    elif args.validate_athena:
        run_validate_athena()
    elif args.flow:
        run_full_flow(args.count, args.seed)

if __name__ == "__main__":
    main()
