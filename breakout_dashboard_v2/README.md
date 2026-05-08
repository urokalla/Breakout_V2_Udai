# Breakout Dashboard V2 (Isolated Project)

This is a separate Reflex project for breakout/timing pages, isolated from the main dashboard app.

## Run with Docker Compose

From `breakout_dashboard_v2_repo` folder:

```bash
docker compose -f docker-compose.breakout-v2.yml up -d --build
```

Open:

- Frontend: `http://localhost:3002`
- Backend: `http://localhost:8002`

Stop:

```bash
docker compose -f docker-compose.breakout-v2.yml down
```

## Design Notes

- Separate app folder/repo path: `breakout_dashboard_v2`
- Keeps current project runtime intact
- Reuses existing storage dependencies:
  - Postgres (`db`)
  - Historical parquet (`./fyers_data_pipeline/data/historical`, mounted read-only)
- Imports breakout/timing modules from existing backend package initially for parity

