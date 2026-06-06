"""Export samples and serve them over a small HTTP API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .store import SampleStore


def export_json(store: SampleStore, out_path: str | Path, kind: Optional[str] = None) -> int:
    dicts = store.all_dicts(kind=kind)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dicts, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(dicts)


def create_app(store: SampleStore):
    """Build a small FastAPI app exposing the stored vitals (needs `pip install .[api]`)."""
    from fastapi import FastAPI

    app = FastAPI(title="CareLoop Garmin vitals", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "samples": store.count(), "kinds": store.kinds()}

    @app.get("/vitals")
    def vitals(kind: Optional[str] = None, limit: Optional[int] = None):
        return store.all_dicts(kind=kind, limit=limit)

    @app.get("/vitals/latest")
    def latest():
        return store.latest_per_kind()

    return app
