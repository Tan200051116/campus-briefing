from __future__ import annotations

import base64
import csv
import io
import os
import re
import unicodedata
import zlib
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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
    cutoff = date.today() - timedelta(days=1)

    for page_number in range(1, max_pages + 1):
        response = session.get(_page_url(page_number), timeout=25)
        response.raise_for_status()
        soup = BeautifulSoup(_decode_official_html(response.text), "html.parser")
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
        events.extend(page_events)
        dated = [date.fromisoformat(e["date"]) for e in page_events if e["date"]]
        if saw_upcoming and dated and max(dated) < cutoff:
            break

    return events


def _read_clipboard(page, cell_range: str) -> str:
    name_box = page.locator("input.edit-box")
    name_box.fill(cell_range)
    name_box.press("Enter")
    page.wait_for_timeout(250)
    canvas = page.locator("canvas.et_main_canvas")
    canvas.click(position={"x": 160, "y": 90}, force=True)
    page.keyboard.press("Control+C")
    page.wait_for_timeout(250)
    return page.evaluate("async () => await navigator.clipboard.readText()")


def _parse_sheet_tsv(text: str, sheet: str) -> list[dict]:
    rows = list(csv.reader(io.StringIO(text), dialect="excel-tab"))
    if not rows:
        return []
    header = [unicodedata.normalize("NFKC", value).strip() for value in rows[0]]

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
        raise RuntimeError(f"共享表格 {sheet} 没有找到“单位名称”列")

    def value(row: list[str], key: str) -> str:
        index = columns[key]
        return row[index].strip() if index is not None and index < len(row) else ""

    result = []
    for row_number, row in enumerate(rows[1:], start=2):
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
    sheet_names = sheets or DEFAULT_SHEETS
    all_rows: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(locale="zh-CN")
        context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://www.kdocs.cn",
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.locator("input.edit-box").wait_for(state="visible", timeout=45_000)
            if "account.wps.cn" in page.url:
                raise RuntimeError("共享表格要求登录，请检查公开分享权限")

            for sheet_name in sheet_names:
                try:
                    page.get_by_text(sheet_name, exact=True).last.click(timeout=8_000)
                    page.wait_for_timeout(350)
                    text = _read_clipboard(page, cell_range)
                    if not text.strip():
                        raise RuntimeError("复制结果为空")
                    all_rows.extend(_parse_sheet_tsv(text, sheet_name))
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError(f"没有找到工作表标签：{sheet_name}") from exc
        finally:
            browser.close()
    return all_rows


def _normalized_company(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"【.*?】|\[.*?\]", "", value)
    value = re.sub(r"20\d{2}届", "", value)
    value = re.sub(r"(秋季|春季|全球|校园|应届生|毕业生|专场|空中)?(招聘|招录|宣讲会|宣讲)", "", value)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value)


def _match_score(official: dict, shared: dict) -> float:
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
    used_shared: set[str] = set()
    merged: list[dict] = []

    for official in official_events:
        best = None
        best_score = 0.0
        for shared in shared_rows:
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
        merged.append(item)

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
            merged.append(item)

    return sorted(merged, key=lambda item: item.get("datetime") or "9999")
