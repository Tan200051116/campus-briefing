from __future__ import annotations

import json
import os
from pathlib import Path

from scrapers import scrape_official


root = Path(__file__).resolve().parent.parent
target = root / "official-events.json"
events = scrape_official(int(os.getenv("OFFICIAL_MAX_PAGES", "30")))
temporary = target.with_suffix(".tmp")
temporary.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
temporary.replace(target)
print(f"wrote {len(events)} events to {target}")
