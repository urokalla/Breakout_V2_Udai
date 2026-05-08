from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import List

from ..config import STORAGE_DATA_ROOT
from ..universes import SYMBOL_GROUPS


@dataclass
class SymbolsAdapter:
    """Phase-2 seam: source symbol universes without SHM dependency."""

    mode: str

    def _load_csv_symbols(self, csv_path: Path) -> list[str]:
        if not csv_path.exists():
            return []
        out: list[str] = []
        try:
            with csv_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Column naming differs across NSE files (Symbol/symbol/SYMBOL).
                    row_ci = {str(k).strip().lower(): v for k, v in row.items()}
                    sym = str(row_ci.get("symbol") or "").strip().upper()
                    if sym:
                        out.append(sym)
            if out:
                return sorted(set(out))
        except Exception:
            return []
        return []

    def list_symbols(self, universe: str) -> List[str]:
        # Prefer explicit universe membership from storage CSVs.
        rel = SYMBOL_GROUPS.get(universe)
        if rel is not None:
            csv_path = Path(STORAGE_DATA_ROOT) / rel
            csv_syms = self._load_csv_symbols(csv_path)
            if csv_syms:
                return csv_syms
            # If universe is explicitly configured but backing CSV is missing/empty,
            # do not silently widen to all parquet symbols.
            return []

        # Optional JSON fallback (if a precomputed universe map is present).
        json_path = Path(STORAGE_DATA_ROOT) / "stock_universe_data.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    vals = data.get(universe) or data.get(universe.upper()) or []
                    if isinstance(vals, list):
                        return [str(x).upper() for x in vals if str(x).strip()]
            except Exception:
                pass

        # Last fallback: derive from available parquet files.
        base = Path("/app/data/historical")
        symbols = sorted({p.stem.upper() for p in base.glob("*.parquet") if p.stem})
        if symbols:
            return symbols
        return []

