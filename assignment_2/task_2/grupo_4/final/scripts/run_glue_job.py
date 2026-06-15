"""Start the incremental Glue job and poll until SUCCEEDED or FAILED."""

from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = ROOT / "terraform"


def _terraform_output(name: str) -> str:
    result = subprocess.run(
        ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-raw", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _start_job(job_name: str) -> str:
    result = subprocess.run(
        ["aws", "glue", "start-job-run", "--job-name", job_name, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return payload["JobRunId"]


def _job_state(job_name: str, run_id: str) -> str:
    result = subprocess.run(
        [
            "aws",
            "glue",
            "get-job-run",
            "--job-name",
            job_name,
            "--run-id",
            run_id,
            "--query",
            "JobRun.JobRunState",
            "--output",
            "text",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run_command(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _terraform_output(name: str) -> str:
    return _run_command(
        ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-raw", name]
    )


def _start_job(job_name: str) -> str:
    payload = json.loads(
        _run_command(
            [
                "aws",
                "glue",
                "start-job-run",
                "--job-name",
                job_name,
                "--output",
                "json",
            ]
        )
    )
    return payload["JobRunId"]


def _job_state(job_name: str, run_id: str) -> str:
    return _run_command(
        [
            "aws",
            "glue",
            "get-job-run",
            "--job-name",
            job_name,
            "--run-id",
            run_id,
            "--query",
            "JobRun.JobRunState",
            "--output",
            "text",
        ]
    )


def _wait_for_job(
    *,
    job_name: str,
    run_id: str,
    poll_seconds: int,
    timeout_seconds: int,
) -> bool:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        state = _job_state(job_name, run_id)

        print(f"  state={state}")

        if state == "SUCCEEDED":
            return True

        if state in {"FAILED", "STOPPED", "TIMEOUT", "ERROR"}:
            return False

        time.sleep(poll_seconds)

    raise TimeoutError("Timed out waiting for Glue job.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run incremental Glue ETL and wait for completion."
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help="Polling interval.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
        help="Max wait time.",
    )
    args = parser.parse_args()

    try:
        job_name = _terraform_output("glue_job_name")

        print(f"Starting Glue job: {job_name}")

        run_id = _start_job(job_name)
        print(f"JobRunId: {run_id}")

        success = _wait_for_job(
            job_name=job_name,
            run_id=run_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )

        if success:
            print("Glue job finished successfully.")
            return 0

        print("Glue job failed.", file=sys.stderr)
        return 1

    except subprocess.CalledProcessError as exc:
        error = exc.stderr.strip() if exc.stderr else str(exc)
        print(error, file=sys.stderr)
        return 1

    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
