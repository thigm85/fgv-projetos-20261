#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time

import boto3
from botocore.exceptions import ClientError

TERMINAL_SUCCESS = {"SUCCEEDED"}
TERMINAL_FAILURE = {"FAILED", "STOPPED", "TIMEOUT", "ERROR"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a Glue job and wait until completion."
    )
    parser.add_argument("--job-name", required=True, help="Glue job name")
    parser.add_argument("--region", required=True, help="AWS region")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=20,
        help="Seconds between job status checks",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
        help="Maximum seconds to wait for job completion",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    glue = boto3.client("glue", region_name=args.region)

    try:
        run_id = glue.start_job_run(JobName=args.job_name)["JobRunId"]
    except ClientError as exc:
        print(f"[glue-job] Failed to start job {args.job_name}: {exc}", file=sys.stderr)
        return 1

    print(f"[glue-job] job={args.job_name}")
    print(f"[glue-job] run_id={run_id}")

    max_polls = max(1, math.ceil(args.timeout_seconds / max(1, args.poll_interval)))
    polls = 0
    while True:
        polls += 1
        if polls > max_polls:
            print("[glue-job] Timeout waiting for Glue job completion.", file=sys.stderr)
            return 1

        response = glue.get_job_run(JobName=args.job_name, RunId=run_id)
        run = response.get("JobRun", {})
        state = run.get("JobRunState", "UNKNOWN")
        print(f"[glue-job] state={state}")

        if state in TERMINAL_SUCCESS:
            print("[glue-job] Glue job succeeded.")
            return 0
        if state in TERMINAL_FAILURE:
            message = run.get("ErrorMessage", "(no error message)")
            print(f"[glue-job] Glue job failed: {message}", file=sys.stderr)
            return 1

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
