import os


def _norm_mode(value: str) -> str:
    s = str(value or "").strip().lower()
    if s in ("storage_only", "legacy_bridge"):
        return s
    return "storage_only"


DATA_MODE = _norm_mode(os.getenv("BREAKOUT_V2_DATA_MODE", "storage_only"))
PIPELINE_DATA_DIR = os.getenv("PIPELINE_DATA_DIR", "/app/data/historical")
DB_HOST = os.getenv("DB_HOST", "db")
STORAGE_DATA_ROOT = os.getenv("BREAKOUT_V2_STORAGE_DATA_ROOT", "/app/stock_scanner_sovereign/data")
SCANNER_API_URL = os.getenv("BREAKOUT_V2_SCANNER_API_URL", "").strip()

