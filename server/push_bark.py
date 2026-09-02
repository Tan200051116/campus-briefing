from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def read_events(path: str) -> list[dict]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


parser = argparse.ArgumentParser()
parser.add_argument("--events-file", default="")
parser.add_argument("--test", action="store_true")
args = parser.parse_args()

bark_url = os.getenv("BARK_URL", "").strip().rstrip("/")
if not bark_url:
    print("BARK_URL is not configured; skipping push")
    raise SystemExit(0)
if not bark_url.startswith("https://"):
    raise SystemExit("BARK_URL must start with https://")

if args.test:
    title = "宣讲工作台测试"
    body = "Bark 推送通道配置成功。以后发现新增宣讲时会自动通知你。"
else:
    events = read_events(args.events_file)
    if not events:
        print("No new briefings; skipping Bark push")
        raise SystemExit(0)
    title = f"发现 {len(events)} 场新增宣讲"
    lines = []
    for event in events[:5]:
        company = event.get("company") or event.get("title") or "未命名企业"
        schedule = event.get("datetime") or event.get("time") or "时间待定"
        location = event.get("location") or "地点待定"
        lines.append(f"{company}\n{schedule} · {location}")
    if len(events) > 5:
        lines.append(f"另有 {len(events) - 5} 场，请打开工作台查看")
    body = "\n\n".join(lines)

payload = json.dumps(
    {
        "title": title,
        "body": body,
        "group": "campus-briefing",
        "isArchive": "1",
    },
    ensure_ascii=False,
).encode("utf-8")
request = Request(
    bark_url,
    data=payload,
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)

try:
    with urlopen(request, timeout=20) as response:
        if not 200 <= response.status < 300:
            raise SystemExit(f"Bark returned HTTP {response.status}")
except HTTPError as error:
    raise SystemExit(f"Bark returned HTTP {error.code}") from None
except URLError:
    raise SystemExit("Bark request failed because of a network error") from None

print("Bark push sent")
