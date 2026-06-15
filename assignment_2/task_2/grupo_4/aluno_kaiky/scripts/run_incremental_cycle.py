"""
Evidence cycle (enunciado 3.4): simulate new orders (Task 1) -> Glue incremental -> validate S3.
"""

from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK1_ROOT = ROOT.parents[2] / "task_1" / "grupo_4" / "aluno_kaiky"
SIMULATE_SCRIPT = TASK1_ROOT / "scripts" / "simulate_new_orders.py"
VALIDATE_SOURCE = TASK1_ROOT / "scripts" / "validate_incremental_source.py"


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one incremental demo cycle.")
    parser.add_argument("--count", type=int, default=5, help="Orders to simulate via Task 1.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--skip-simulate", action="store_true", help="Only run Glue + S3 validation.")
    parser.add_argument("--require-pending", action="store_true", help="Validate Task 1 source before ETL.")
    args = parser.parse_args()

    if args.require_pending and not args.skip_simulate:
        code = _run([sys.executable, str(VALIDATE_SOURCE), "--require-pending"], cwd=TASK1_ROOT)
        if code != 0:
            return code

    if not args.skip_simulate:
        sim_cmd = [sys.executable, str(SIMULATE_SCRIPT), "--count", str(args.count)]
        if args.seed is not None:
            sim_cmd.extend(["--seed", str(args.seed)])
        code = _run(sim_cmd, cwd=TASK1_ROOT)
        if code != 0:
            return code

        code = _run([sys.executable, str(VALIDATE_SOURCE), "--require-pending"], cwd=TASK1_ROOT)
        if code != 0:
            return code

    code = _run([sys.executable, str(ROOT / "scripts" / "run_glue_job.py")])
    if code != 0:
        return code

    return _run([sys.executable, str(ROOT / "scripts" / "validate_etl_output.py")])


if __name__ == "__main__":
    raise SystemExit(main())
