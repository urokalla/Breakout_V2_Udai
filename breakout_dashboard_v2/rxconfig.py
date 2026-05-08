import os

import reflex as rx

_api = (os.getenv("REFLEX_API_URL") or os.getenv("API_URL") or "http://localhost:3002").strip()

config = rx.Config(
    app_name="breakout_v2_app",
    api_url=_api,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)

