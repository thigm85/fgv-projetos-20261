import argparse

from utils.tasks import (
    task_simulate_orders
)


parser = argparse.ArgumentParser()

parser.add_argument(
    "--count",
    type=int,
    default=5
)

parser.add_argument(
    "--seed",
    type=int
)

args = parser.parse_args()

raise SystemExit(
    task_simulate_orders(
        count=args.count,
        seed=args.seed
    )
)