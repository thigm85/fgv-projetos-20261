#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time

import boto3
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a Glue crawler and wait until it finishes."
    )
    parser.add_argument("--crawler-name", required=True, help="Glue crawler name")
    parser.add_argument("--region", required=True, help="AWS region")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=20,
        help="Seconds between crawler status checks",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Maximum seconds to wait for crawler completion",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    glue = boto3.client("glue", region_name=args.region)
    start_time = time.monotonic()

    try:
        state = glue.get_crawler(Name=args.crawler_name)["Crawler"]["State"]
        if state != "READY":
            print(f"[crawler] Current state is {state}; waiting for READY before start.")
            while state != "READY":
                if time.monotonic() - start_time > args.timeout_seconds:
                    print("[crawler] Timeout waiting for crawler to become READY.", file=sys.stderr)
                    return 1
                time.sleep(args.poll_interval)
                state = glue.get_crawler(Name=args.crawler_name)["Crawler"]["State"]

        print(f"[crawler] Starting crawler {args.crawler_name}...")
        glue.start_crawler(Name=args.crawler_name)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "CrawlerRunningException":
            print(f"[crawler] Crawler {args.crawler_name} is already running.")
        else:
            print(f"[crawler] Failed to start crawler: {exc}", file=sys.stderr)
            return 1

    max_polls = max(1, math.ceil(args.timeout_seconds / max(1, args.poll_interval)))
    polls = 0
    while True:
        polls += 1
        if polls > max_polls:
            print("[crawler] Timeout waiting for crawler completion.", file=sys.stderr)
            return 1

        crawler = glue.get_crawler(Name=args.crawler_name)["Crawler"]
        state = crawler.get("State", "UNKNOWN")
        last_status = crawler.get("LastCrawl", {}).get("Status", "UNKNOWN")
        print(f"[crawler] state={state} last_status={last_status}")

        if state == "READY":
            if last_status in {"SUCCEEDED"}:
                print("[crawler] Crawler finished successfully.")
                return 0
            if last_status in {"FAILED", "CANCELLED"}:
                print("[crawler] Crawler failed.", file=sys.stderr)
                return 1
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
