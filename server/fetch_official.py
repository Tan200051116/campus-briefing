from __future__ import annotations

import json
import os
from pathlib import Path

from scrapers import scrape_official


def load_events(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


root = Path(__file__).resolve().parent.parent
target = root / "official-events.json"
previous = load_events(target)
events = scrape_official(int(os.getenv("OFFICIAL_MAX_PAGES", "30")))

# 官网偶发超时或返回异常页面时，绝不能用空数组覆盖上一份完整数据。
if not events:
    raise RuntimeError("官网抓取结果为空，已保留仓库中的上一份数据")

previous_ids = {str(item.get("id")) for item in previous if item.get("id")}
new_events = [item for item in events if item.get("id") and str(item["id"]) not in previous_ids]

temporary = target.with_suffix(".tmp")
temporary.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
temporary.replace(target)

new_events_file = os.getenv("NEW_EVENTS_FILE", "").strip()
if new_events_file:
    Path(new_events_file).write_text(
        json.dumps(new_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

print(f"wrote {len(events)} events to {target}; new={len(new_events)}")
