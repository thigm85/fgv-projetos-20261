#!/usr/bin/env bash
set -euo pipefail

COUNT="${COUNT:-5}"
SEED="${SEED:-42}"
PYTHON="${PYTHON:-python3}"

"$PYTHON" scripts/init_watermark.py
"$PYTHON" scripts/validate_incremental_source.py
"$PYTHON" scripts/simulate_new_orders.py --count "$COUNT" --seed "$SEED"
"$PYTHON" scripts/validate_incremental_source.py --require-pending
