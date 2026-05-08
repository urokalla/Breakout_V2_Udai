#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/udairokalla/breakout_dashboard_v2_repo"
COMPOSE_FILE="$ROOT/docker-compose.breakout-v2.yml"

MODE="${1:-}"
if [[ "$MODE" != "shm" && "$MODE" != "dragonfly" ]]; then
  echo "Usage: $0 shm|dragonfly"
  exit 1
fi

echo "Switching V2 live source to: $MODE"
BREAKOUT_V2_LIVE_SOURCE="$MODE" docker compose -f "$COMPOSE_FILE" up -d --force-recreate dashboard_breakout_v2

echo "Verifying runtime source..."
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
from breakout_v2_app.engine import get_engine
rows = get_engine().snapshot(universe='Nifty 50').get('daily_rows', [])
sources = sorted(set(str(r.get('quote_source') or '') for r in rows))
print("quote_sources=", sources)
print("rows=", len(rows))
PY

echo "Done."

