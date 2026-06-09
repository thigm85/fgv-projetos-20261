"""
Orquestra o fluxo da Task 1 APÓS o provisionamento do RDS (infra/ via terraform apply).

Ordem:
  1. load_classicmodels          → carrega o dump no RDS recém-criado
  2. init_watermark              → cria/inicializa etl_watermark
  3. validate_incremental_source → baseline (sem pendência exigida)
  4. simulate_new_orders --count N → insere pedidos novos
  5. validate_incremental_source --require-pending → exige dados pendentes

Uso:
  python pipeline.py                 # fluxo completo (load + setup + simulação)
  python pipeline.py --skip-load     # pula a carga (banco já carregado)
  python pipeline.py --count 10 --seed 42
"""
import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
PYTHON = sys.executable


def run(name: str, argv: list) -> None:
    print(f"\n{'='*60}\n>> {name}\n{'='*60}")
    result = subprocess.run([PYTHON, *argv], cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"\n[PARADO] Etapa '{name}' falhou (exit {result.returncode}).")
        sys.exit(result.returncode)


def main() -> int:
    p = argparse.ArgumentParser(description="Orquestra o setup incremental da Task 1.")
    p.add_argument("--skip-load", action="store_true", help="Pula a carga do classicmodels.")
    p.add_argument("--count", type=int, default=5, help="Pedidos a simular (default 5).")
    p.add_argument("--seed", type=int, default=None, help="Seed da simulação (opcional).")
    args = p.parse_args()

    if not args.skip_load:
        run("Carga do classicmodels", ["load_classicmodels.py"])

    run("Inicialização do watermark", ["init_watermark.py"])
    run("Validação baseline", ["validate_incremental_source.py"])

    sim_argv = ["simulate_new_orders.py", "--count", str(args.count)]
    if args.seed is not None:
        sim_argv += ["--seed", str(args.seed)]
    run("Simulação de novos pedidos", sim_argv)

    run("Validação com dados pendentes", ["validate_incremental_source.py", "--require-pending"])

    print(f"\n{'='*60}\nFluxo da Task 1 concluído com sucesso.\n{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
