"""
Executa o pipeline completo na ordem correta:
  1. Carrega classicmodels no RDS
  2. Valida o RDS
  3. Executa o Glue ETL job e aguarda SUCCEEDED
  4. Valida o output do ETL no S3

Uso:
  python pipeline.py            # execução normal
  python pipeline.py --dry-run  # simula sem fazer alterações destrutivas
"""
import subprocess
import sys
from pathlib import Path

BASE_DIR  = Path(__file__).parent
PYTHON    = sys.executable
DRY_RUN   = "--dry-run" in sys.argv

STEPS = [
    ("Carga do RDS",         BASE_DIR / "2_load_data.py",   True),
    ("Validação do RDS",     BASE_DIR / "3_validate_data.py", False),
    ("Execução do Glue job", BASE_DIR / "run_job.py",        True),
    ("Validação do ETL",     BASE_DIR / "validate_etl.py",   False),
]

if DRY_RUN:
    print("=" * 55)
    print("[DRY-RUN] Simulação do pipeline — nenhuma ação destrutiva será executada.")
    print("=" * 55)

for i, (name, script, supports_dry_run) in enumerate(STEPS, 1):
    print(f"\n{'='*55}")
    print(f"[{i}/{len(STEPS)}] {name}")
    print("=" * 55)

    cmd = [PYTHON, str(script)]
    if DRY_RUN and supports_dry_run:
        cmd.append("--dry-run")
    elif DRY_RUN and not supports_dry_run:
        print(f"[DRY-RUN] Pulando etapa de leitura/validação (sem efeitos colaterais).")
        continue

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n[PARADO] Etapa '{name}' falhou. Corrija o erro antes de continuar.")
        sys.exit(result.returncode)

print(f"\n{'='*55}")
if DRY_RUN:
    print("Simulação concluída. Rode sem --dry-run para executar de verdade.")
else:
    print("Pipeline concluído com sucesso.")
print("=" * 55)
