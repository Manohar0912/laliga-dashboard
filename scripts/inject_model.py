#!/usr/bin/env python3
"""Embed the trained prediction payload into the standalone dashboard HTML."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "model_predictions.json"
HTML = ROOT / "index.html"

payload = json.loads(MODEL.read_text(encoding="utf-8"))
html = HTML.read_text(encoding="utf-8")
marker = "<script>\nconst DATA="
if marker not in html:
    raise RuntimeError("Could not find dashboard script marker for model injection")
compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
html = html.replace(marker, f"<script>\nconst PREDICTION_MODEL={compact};\nconst DATA=", 1)
HTML.write_text(html, encoding="utf-8")
print(f"Embedded prediction model {payload.get('version')} with {len(payload.get('predictions', {}))} fixture predictions")
