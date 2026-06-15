#!/usr/bin/env python3
"""
Task 2 entrypoint: deploy Terraform, run incremental Glue, or full demo cycle.
"""

from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TERRAFORM_DIR = ROOT / "terraform"


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd).returncode


def cmd_deploy(_: argparse.Namespace) -> int:
    if _run(["terraform", f"-chdir={TERRAFORM_DIR}", "init"]) != 0:
        return 1
    return _run(["terraform", f"-chdir={TERRAFORM_DIR}", "apply", "-auto-approve"])


def cmd_run_etl(_: argparse.Namespace) -> int:
    return _run([sys.executable, str(ROOT / "scripts" / "run_glue_job.py")])


def cmd_demo(args: argparse.Namespace) -> int:
    cycle_cmd = [sys.executable, str(ROOT / "scripts" / "run_incremental_cycle.py"), "--count", str(args.count)]
    if args.seed is not None:
        cycle_cmd.extend(["--seed", str(args.seed)])
    return _run(cycle_cmd)


def cmd_full(args: argparse.Namespace) -> int:
    if cmd_deploy(args) != 0:
        return 1
    return cmd_demo(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assignment 2 Task 2 — incremental ETL operations.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("deploy", help="terraform init && apply -auto-approve").set_defaults(func=cmd_deploy)
    sub.add_parser("run-etl", help="Start Glue job and wait for completion").set_defaults(func=cmd_run_etl)

    demo = sub.add_parser("demo", help="simulate (Task 1) -> Glue -> validate S3")
    demo.add_argument("--count", type=int, default=5)
    demo.add_argument("--seed", type=int, default=None)
    demo.set_defaults(func=cmd_demo)

    full = sub.add_parser("full", help="deploy + demo")
    full.add_argument("--count", type=int, default=5)
    full.add_argument("--seed", type=int, default=None)
    full.set_defaults(func=cmd_full)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
