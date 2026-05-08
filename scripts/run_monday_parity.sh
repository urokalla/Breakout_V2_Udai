#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/udairokalla/breakout_dashboard_v2_repo"

# Default larger sample for Monday checks; override by exporting PARITY_SYMBOLS before running.
export PARITY_SYMBOLS="${PARITY_SYMBOLS:-RELIANCE,TCS,INFY,ICICIBANK,HDFCBANK,AXISBANK,SBIN,LT,ITC,KOTAKBANK,BAJFINANCE,BHARTIARTL,ASIANPAINT,HCLTECH,TITAN}"

echo "Running Dragonfly parity validation..."
docker exec -i sovereign_dashboard_breakout_v2 python /app/breakout_dashboard_v2/scripts/validate_dragonfly_parity.py

echo "Latest summary artifact:"
ls -t "$ROOT/breakout_dashboard_v2/runtime"/dragonfly_parity_summary_*.json | head -n 1

