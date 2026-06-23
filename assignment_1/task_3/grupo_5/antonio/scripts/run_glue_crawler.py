#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    glue = boto3.client("glue", region_name=args.region)

    try:
        state = glue.get_crawler(Name=args.crawler_name)["Crawler"]["State"]
        if state != "READY":
            print(f"[crawler] Current state is {state}; waiting for READY before start.")
            while state != "READY":
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

    while True:
        crawler = glue.get_crawler(Name=args.crawler_name)["Crawler"]
        state = crawler.get("State", "UNKNOWN")
        last_status = crawler.get("LastCrawl", {}).get("Status", "UNKNOWN")
        print(f"[crawler] state={state} last_status={last_status}")

        if state == "READY":
            if last_status in {"SUCCEEDED", "CANCELLED"}:
                print("[crawler] Crawler finished successfully.")
                return 0
            if last_status in {"FAILED"}:
                print("[crawler] Crawler failed.", file=sys.stderr)
                return 1
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
