from __future__ import annotations

import base64
import os
import re
import time
import unicodedata
import zlib
from datetime import date, datetime
from difflib import SequenceMatcher
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


OFFICIAL_BASE = "https://myjob.dlmu.edu.cn"
OFFICIAL_LIST = f"{OFFICIAL_BASE}/teachin/index"
DEFAULT_SHEETS = [
    "第一周（8.31-9.6）", "第二周（9.7-9.13）", "第三周（9.14-9.20）",
    "第四周（9.21-9.27）", "第五周（9.28-10.4）", "第六周（10.5-10.11）",
    "第七周（10.12-10.18）", "第八周（10.19-10.25）", "第九周（10.26-11.1）",
    "第十周（11.2-11.8）", "第十一周（11.9-11.15）", "第十二周（11.16-11.22）",
    "第十三周（11.23-11.29）", "第十四周（11.30-12.6）", "第十五周（12.7-12.13）",
    "第十六周（12.14-12.20）",
]


def _local_today() -> date:
    timezone_name = os.getenv("LOCAL_TIMEZONE", "Asia/Shanghai")
    return datetime.now(ZoneInfo(timezone_name)).date()


def _is_today_or_future(item: dict) -> bool:
    value = item.get("date", "")
    if not value:
        return False
    try:
        return date.fromisoformat(value) >= _local_today()
    except ValueError:
        return False


def _decode_official_html(page_html: str) -> str:
    match = re.search(r'unzip\("([A-Za-z0-9+/=]+)"\)', page_html)
    if not match:
        raise RuntimeError("官网页面结构已变化：没有找到压缩数据")
    first = zlib.decompress(base64.b64decode(match.group(1))).decode("utf-8", "ignore")
    marker = first.find("dmlldzFk")
    if marker < 0:
        raise RuntimeError("官网页面结构已变化：没有找到二次编码数据")
    second = "".join(first[marker:].split())
    return base64.b64decode(second).decode("utf-8", "ignore")


def _page_url(page: int) -> str:
    if page == 1:
        return OFFICIAL_LIST
    return f"{OFFICIAL_LIST}/do123/myjob.dlmu.edu.cn/domain/myjob/page/{page}"


def scrape_official(max_pages: int = 30) -> list[dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": "CampusBriefingBot/1.0 (+personal VPS)"})
    events: list[dict] = []
    seen: set[str] = set()
    saw_upcoming = False
    cutoff = _local_today()

    for page_number in range(1, max_pages + 1):
        last_error = None
        for attempt in range(3):
            try:
                response = session.get(_page_url(page_number), timeout=(10, 30))
                response.raise_for_status()
                soup = BeautifulSoup(_decode_official_html(response.text), "html.parser")
                break
            except (requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            raise RuntimeError(
                f"官网第 {page_number} 页连续抓取失败"
            ) from last_error
        page_events: list[dict] = []

        for row in soup.select("ul.infoList.teachinList"):
            link = row.select_one("li.span9 a")
            place = row.select_one("li.span5")
            time_cell = row.select_one("li.span3")
            kind = row.select_one(".status-text")
            if not (link and time_cell):
                continue
            href = link.get("href", "")
            match = re.search(r"/id/(\d+)", href)
            event_id = match.group(1) if match else href
            if event_id in seen:
                continue
            seen.add(event_id)
            time_text = time_cell.get_text(" ", strip=True)
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", time_text)
            event_date = date_match.group(0) if date_match else ""
            item = {
                "id": f"official-{event_id}",
                "title": link.get("title") or link.get_text(" ", strip=True),
                "company": link.get("title") or link.get_text(" ", strip=True),
                "kind": kind.get_text(" ", strip=True) if kind else "宣讲",
                "location": place.get_text(" ", strip=True) if place else "",
                "datetime": time_text,
                "date": event_date,
                "official_url": urljoin(OFFICIAL_BASE, href),
                "source": "official",
                "source_label": "就业网",
            }
            page_events.append(item)
            if event_date and date.fromisoformat(event_date) >= cutoff:
                saw_upcoming = True

        if not page_events:
            break
        events.extend(event for event in page_events if _is_today_or_future(event))
        dated = [date.fromisoformat(e["date"]) for e in page_events if e["date"]]
        if saw_upcoming and dated and max(dated) < cutoff:
            break

    return events


def fetch_official_feed(url: str) -> list[dict]:
    response = requests.get(
        url,
        headers={"User-Agent": "CampusBriefingVPS/1.0", "Cache-Control": "no-cache"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        raise RuntimeError("官网数据中转文件格式不正确")
    return [dict(event) for event in events if isinstance(event, dict)]


def _read_workbook(page, row_limit: int = 200, col_limit: int = 9) -> list[dict]:
    return page.evaluate(
        """
({rowLimit, colLimit}) => {
  const worksheets = window.APP.getWorksheets();
  const sheets = (worksheets && worksheets._sheets) || [];
  return sheets.map((sheet) => {
    let name = "";
    try { name = String(sheet.getName() || "").trim(); } catch (e) {}
    const rows = [];
    for (let r = 0; r < rowLimit; r++) {
      const cells = [];
      for (let c = 0; c < colLimit; c++) {
        let value = "";
        try {
          const raw = sheet.getCellString(r, c);
          value = raw == null ? "" : String(raw).trim();
        } catch (e) {}
        cells.push(value);
      }
      rows.push(cells);
    }
    return {name, rows};
  });
}
        """,
        {"rowLimit": row_limit, "colLimit": col_limit},
    )


def _parse_sheet_rows(rows: list[list[str]], sheet: str) -> list[dict]:
    if not rows:
        return []

    # 周表可能在顶部留出标题、说明或空白区域，不能假定第一行就是表头。
    header_index = None
    header = []
    for index, row in enumerate(rows):
        normalized = [unicodedata.normalize("NFKC", value).strip() for value in row]
        if any("单位名称" in value for value in normalized) and any(
            "宣讲时间" in value for value in normalized
        ):
            header_index = index
            header = normalized
            break
    if header_index is None:
        return []

    def find_col(*needles: str) -> int | None:
        for index, value in enumerate(header):
            if any(needle in value for needle in needles):
                return index
        return None

    columns = {
        "company": find_col("单位名称", "单位"),
        "time": find_col("宣讲时间", "时间"),
        "location": find_col("宣讲地址", "地址", "地点"),
        "leader": find_col("组长"),
        "members": find_col("组员"),
        "contact": find_col("组长联系方式", "联系方式"),
        "contacted": find_col("是否已经联系", "是否联系"),
        "notes": find_col("备注"),
    }
    if columns["company"] is None:
        return []

    def value(row: list[str], key: str) -> str:
        index = columns[key]
        return row[index].strip() if index is not None and index < len(row) else ""

    result = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        company = value(row, "company")
        if not company:
            continue
        time_text = value(row, "time")
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", time_text)
        result.append({
            "id": f"shared-{sheet}-{row_number}",
            "company": company,
            "title": company,
            "time": time_text,
            "datetime": time_text,
            "date": date_match.group(0) if date_match else "",
            "location": value(row, "location"),
            "leader": value(row, "leader"),
            "members": value(row, "members"),
            "contact": value(row, "contact"),
            "contacted": value(row, "contacted"),
            "notes": value(row, "notes"),
            "sheet": sheet,
            "source": "shared",
            "source_label": "共享表格",
        })
    return result


def scrape_kdocs(url: str, cell_range: str = "A1:I200", sheets: list[str] | None = None) -> list[dict]:
    wanted_sheets = {name.strip() for name in (sheets or DEFAULT_SHEETS)}
    all_rows: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.locator("input.edit-box").wait_for(state="visible", timeout=45_000)
            if "account.wps.cn" in page.url:
                raise RuntimeError("共享表格要求登录，请检查公开分享权限")
            page.wait_for_function(
                "() => window.APP && window.APP.getWorksheets && "
                "window.APP.getWorksheets()._sheets && window.APP.getWorksheets()._sheets.length",
                timeout=45_000,
            )

            for sheet_data in _read_workbook(page):
                sheet_name = str(sheet_data.get("name", "")).strip()
                if not sheet_name or sheet_name not in wanted_sheets:
                    continue
                rows = sheet_data.get("rows") or []
                all_rows.extend(_parse_sheet_rows(rows, sheet_name))
        finally:
            browser.close()
    return all_rows


def _normalized_company(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"【.*?】|\[.*?\]", "", value)
    value = re.sub(r"20\d{2}届", "", value)
    value = re.sub(r"(秋季|春季|全球|校园|应届生|毕业生|专场|空中)?(招聘|招录|宣讲会|宣讲)", "", value)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value)


def _schedule_time_key(item: dict) -> str:
    value = unicodedata.normalize(
        "NFKC", item.get("datetime") or item.get("time") or ""
    )
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    time_match = re.search(
        r"(\d{1,2}:\d{2})\s*(?:-|—|–|~|～|至|到)\s*(\d{1,2}:\d{2})",
        value,
    )
    if date_match and time_match:
        return f"{date_match.group(0)}|{time_match.group(1)}-{time_match.group(2)}"
    return re.sub(r"\s+", "", value)


def _match_score(official: dict, shared: dict) -> float:
    official_time = _schedule_time_key(official)
    shared_time = _schedule_time_key(shared)
    official_location = re.sub(
        r"\s+", "", unicodedata.normalize("NFKC", official.get("location") or "")
    ).removeprefix("大连海事大学")
    shared_location = re.sub(
        r"\s+", "", unicodedata.normalize("NFKC", shared.get("location") or "")
    ).removeprefix("大连海事大学")
    if (
        official_time
        and shared_time
        and official_location
        and shared_location
        and official_time == shared_time
        and official_location == shared_location
    ):
        # 同一时间、同一地点视为同一场，以官网标题和详情为准。
        return 2.0

    left = _normalized_company(official.get("company", ""))
    right = _normalized_company(shared.get("company", ""))
    if not left or not right:
        return 0.0
    if official.get("date") and shared.get("date") and official["date"] != shared["date"]:
        return 0.0
    if left in right or right in left:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def merge_events(official_events: list[dict], shared_rows: list[dict], my_name: str) -> list[dict]:
    official_events = [event for event in official_events if _is_today_or_future(event)]
    shared_rows = [row for row in shared_rows if _is_today_or_future(row)]
    used_shared: set[str] = set()
    seen_events: set[tuple[str, str, str]] = set()
    merged: list[dict] = []

    def dedup_key(item: dict) -> tuple[str, str, str]:
        company = _normalized_company(item.get("company") or item.get("title") or "")
        time_text = unicodedata.normalize(
            "NFKC", item.get("datetime") or item.get("time") or item.get("date") or ""
        )
        location = unicodedata.normalize("NFKC", item.get("location") or "")
        return (
            company,
            re.sub(r"\s+", "", time_text),
            re.sub(r"\s+", "", location),
        )

    def append_unique(item: dict) -> None:
        key = dedup_key(item)
        if key in seen_events:
            return
        seen_events.add(key)
        merged.append(item)

    for official in official_events:
        best = None
        best_score = 0.0
        for shared in shared_rows:
            if shared["id"] in used_shared:
                continue
            score = _match_score(official, shared)
            if score > best_score:
                best, best_score = shared, score
        matched = best if best_score >= 0.72 else None
        item = dict(official)
        item["in_shared_sheet"] = bool(matched)
        item["is_new"] = not matched
        item["is_mine"] = False
        if matched:
            used_shared.add(matched["id"])
            item.update({key: matched.get(key, "") for key in (
                "leader", "members", "contact", "contacted", "notes", "sheet"
            )})
            item["is_mine"] = my_name in f'{matched.get("leader", "")} {matched.get("members", "")}'
        append_unique(item)

    for shared in shared_rows:
        if shared["id"] in used_shared:
            continue
        is_mine = my_name in f'{shared.get("leader", "")} {shared.get("members", "")}'
        if is_mine:
            item = dict(shared)
            item.update({
                "kind": "表格宣讲",
                "official_url": "",
                "in_shared_sheet": True,
                "is_new": False,
                "is_mine": True,
            })
            append_unique(item)

    return sorted(merged, key=lambda item: item.get("datetime") or "9999")
