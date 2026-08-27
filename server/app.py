from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from scrapers import DEFAULT_SHEETS, merge_events, scrape_kdocs, scrape_official


load_dotenv()

INTERVAL_MINUTES = max(5, int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60")))
OFFICIAL_MAX_PAGES = int(os.getenv("OFFICIAL_MAX_PAGES", "30"))
KDOCS_URL = os.getenv("KDOCS_URL", "").strip()
KDOCS_RANGE = os.getenv("KDOCS_RANGE", "A1:I200")
MY_NAME = os.getenv("MY_NAME", "谭睿")
DATA_FILE = Path(os.getenv("DATA_FILE", "./data/snapshot.json"))
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "https://tan200051116.github.io")
KDOCS_SHEETS = [x.strip() for x in os.getenv("KDOCS_SHEETS", "").split(",") if x.strip()] or DEFAULT_SHEETS

app = FastAPI(title="宣讲工作台同步服务", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGIN.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

state_lock = threading.Lock()
stop_event = threading.Event()
state = {
    "events": [],
    "last_attempt": None,
    "last_success": None,
    "errors": {},
}


def _load_snapshot() -> None:
    if not DATA_FILE.exists():
        return
    try:
        loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        with state_lock:
            state.update(loaded)
    except (OSError, json.JSONDecodeError):
        pass


def _save_snapshot() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DATA_FILE.with_suffix(".tmp")
    with state_lock:
        payload = json.dumps(state, ensure_ascii=False, indent=2)
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(DATA_FILE)


def sync_once() -> None:
    attempted_at = datetime.now(timezone.utc).isoformat()
    errors = {}
    official = None
    shared = None

    try:
        official = scrape_official(OFFICIAL_MAX_PAGES)
    except Exception as exc:  # 保存另一来源的成功结果，并在状态接口明确报告错误
        errors["official"] = str(exc)

    if not KDOCS_URL:
        errors["kdocs"] = "未配置 KDOCS_URL"
    else:
        try:
            shared = scrape_kdocs(KDOCS_URL, KDOCS_RANGE, KDOCS_SHEETS)
        except Exception as exc:
            errors["kdocs"] = str(exc)

    with state_lock:
        previous = state.get("events", [])

    if official is not None and shared is not None:
        events = merge_events(official, shared, MY_NAME)
        success_at = datetime.now(timezone.utc).isoformat()
    else:
        events = previous
        success_at = None

    with state_lock:
        state["last_attempt"] = attempted_at
        state["errors"] = errors
        state["events"] = events
        if success_at:
            state["last_success"] = success_at
    _save_snapshot()


def _worker() -> None:
    while not stop_event.is_set():
        sync_once()
        stop_event.wait(INTERVAL_MINUTES * 60)


@app.on_event("startup")
def startup() -> None:
    _load_snapshot()
    threading.Thread(target=_worker, name="briefing-sync", daemon=True).start()


@app.on_event("shutdown")
def shutdown() -> None:
    stop_event.set()


@app.get("/api/status")
def get_status() -> dict:
    with state_lock:
        events = list(state["events"])
        return {
            "ok": bool(state.get("last_success")),
            "last_attempt": state.get("last_attempt"),
            "last_success": state.get("last_success"),
            "errors": dict(state.get("errors", {})),
            "interval_minutes": INTERVAL_MINUTES,
            "counts": {
                "all": len(events),
                "new": sum(bool(e.get("is_new")) for e in events),
                "mine": sum(bool(e.get("is_mine")) for e in events),
            },
        }


@app.get("/api/events")
def get_events(scope: str = Query("all", pattern="^(all|new|mine)$")) -> dict:
    with state_lock:
        events = list(state["events"])
        last_success = state.get("last_success")
    if not events and not last_success:
        raise HTTPException(status_code=503, detail="首次同步尚未成功，请查看 /api/status")
    if scope == "new":
        selected = [event for event in events if event.get("is_new")]
    elif scope == "mine":
        selected = [event for event in events if event.get("is_mine")]
    else:
        selected = events
    return {
        "scope": scope,
        "last_success": last_success,
        "counts": {
            "all": len(events),
            "new": sum(bool(e.get("is_new")) for e in events),
            "mine": sum(bool(e.get("is_mine")) for e in events),
        },
        "events": selected,
    }
