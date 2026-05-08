FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.local/share/reflex/bun/bin:$PATH"
ENV BUN_INSTALL="/root/.bun"
ENV PATH="$BUN_INSTALL/bin:$PATH"

WORKDIR /app

COPY RS_PROJECT/stock_scanner_sovereign/requirements.txt ./scanner_requirements.txt
COPY RS_PROJECT/stock_scanner_sovereign/frontend_reflex/requirements.txt ./reflex_requirements.txt
RUN pip install --no-cache-dir -r ./scanner_requirements.txt
RUN pip install --no-cache-dir -r ./reflex_requirements.txt

COPY RS_PROJECT/stock_scanner_sovereign /app/stock_scanner_sovereign
COPY breakout_dashboard_v2_repo/breakout_dashboard_v2 /app/breakout_dashboard_v2

WORKDIR /app/breakout_dashboard_v2
ENV PYTHONPATH=/app/stock_scanner_sovereign/frontend_reflex:/app/stock_scanner_sovereign:/app/breakout_dashboard_v2
ENV NODE_TLS_REJECT_UNAUTHORIZED=0
ENV BUN_CONFIG_STRICT_SSL=false

RUN bun install || true
RUN reflex init

EXPOSE 3000 8000

CMD ["reflex", "run", "--env", "prod", "--backend-host", "0.0.0.0", "--loglevel", "info"]

