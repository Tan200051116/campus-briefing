from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from scrapers import fetch_official_feed, merge_events, scrape_official


load_dotenv()

INTERVAL_MINUTES = max(5, int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30")))
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Asia/Shanghai")
QUIET_START_HOUR = int(os.getenv("QUIET_START_HOUR", "22"))
QUIET_END_HOUR = int(os.getenv("QUIET_END_HOUR", "8"))
OFFICIAL_MAX_PAGES = int(os.getenv("OFFICIAL_MAX_PAGES", "30"))
OFFICIAL_FEED_URL = os.getenv(
    "OFFICIAL_FEED_URL",
    "https://tan200051116.github.io/campus-briefing/official-events.json",
).strip()
DATA_FILE = Path(os.getenv("DATA_FILE", "./data/snapshot.json"))
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "https://tan200051116.github.io")

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

    try:
        official = (
            fetch_official_feed(OFFICIAL_FEED_URL)
            if OFFICIAL_FEED_URL
            else scrape_official(OFFICIAL_MAX_PAGES)
        )
    except Exception as exc:
        errors["official"] = str(exc)

    with state_lock:
        previous = state.get("events", [])

    if official is not None:
        # 服务端只保留官网事实数据；“我的”和已读状态由浏览器本地维护。
        events = merge_events(official, [], "")
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


def _quiet_seconds_remaining(now: datetime | None = None) -> float:
    local_now = now or datetime.now(ZoneInfo(LOCAL_TIMEZONE))
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=ZoneInfo(LOCAL_TIMEZONE))

    hour = local_now.hour
    if QUIET_START_HOUR < QUIET_END_HOUR:
        is_quiet = QUIET_START_HOUR <= hour < QUIET_END_HOUR
    else:
        is_quiet = hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR
    if not is_quiet:
        return 0

    next_active = local_now.replace(
        hour=QUIET_END_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    if QUIET_START_HOUR >= QUIET_END_HOUR and hour >= QUIET_START_HOUR:
        next_active += timedelta(days=1)
    return max(1, (next_active - local_now).total_seconds())


def _worker() -> None:
    while not stop_event.is_set():
        quiet_wait = _quiet_seconds_remaining()
        if quiet_wait:
            stop_event.wait(quiet_wait)
            continue
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
            "quiet_hours": {
                "timezone": LOCAL_TIMEZONE,
                "start": f"{QUIET_START_HOUR:02d}:00",
                "end": f"{QUIET_END_HOUR:02d}:00",
            },
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
