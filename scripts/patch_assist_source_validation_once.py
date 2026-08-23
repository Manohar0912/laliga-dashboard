#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'scripts' / 'update_season_stats.py'
text = p.read_text(encoding='utf-8')

marker = "\n\ndef now_iso() -> str:"
aliases = '''\n\nAS_PLAYER_ALIASES = {\n    "Mariano": "Mariano Díaz",\n    "Isaac": "Isaac Romero",\n}\n'''
if 'AS_PLAYER_ALIASES' not in text:
    text = text.replace(marker, aliases + marker, 1)
text = text.replace('"name": clean["player"],', '"name": AS_PLAYER_ALIASES.get(clean["player"], clean["player"]),', 1)

start = text.index('def validate_cross_source(')
end = text.index('\ndef refresh_year(', start)
new_validation = '''def validate_cross_source(scorers: list[dict], assists: list[dict], label: str) -> None:\n    """Validate source shape/completeness without assuming providers define assists identically."""\n    if not scorers:\n        raise RuntimeError(f"{label}: goal scorer feed is empty")\n    if not assists:\n        raise RuntimeError(f"{label}: dedicated assists feed is empty")\n    if len(assists) < 3:\n        raise RuntimeError(f"{label}: dedicated assists ranking suspiciously short: {len(assists)} rows")\n    values = [r.get("assists", 0) for r in assists]\n    if values != sorted(values, reverse=True):\n        raise RuntimeError(f"{label}: dedicated assists ranking is not sorted descending")\n    if max(values, default=0) <= 0 and any(r.get("assistsInScorerFeed", 0) > 0 for r in scorers):\n        raise RuntimeError(f"{label}: dedicated assists ranking has zero leaders despite scorer-feed assists")\n\n'''
text = text[:start] + new_validation + text[end:]
p.write_text(text, encoding='utf-8')
print('Relaxed cross-provider equality check; retained structural assist-source validation')
