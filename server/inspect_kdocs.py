from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


load_dotenv()
url = os.getenv("KDOCS_URL", "").strip()
if not url:
    raise SystemExit("KDOCS_URL 未配置")


def safe_path(value: str) -> str:
    parsed = urlsplit(value)
    path = re.sub(r"\d{7,}", "<id>", parsed.path)
    path = re.sub(r"/l/[^/]+", "/l/<share>", path)
    return f"{parsed.netloc}{path}"


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
    responses: dict[str, tuple[int, str]] = {}
    open_responses = []

    def remember(response) -> None:
        content_type = response.headers.get("content-type", "").split(";")[0]
        path = safe_path(response.url)
        lower = path.lower()
        if content_type in {"application/json", "application/octet-stream", "application/x-protobuf"} or any(
            word in lower for word in ("/api/", "sheet", "office", "file", "drive")
        ):
            responses[path] = (response.status, content_type)
        if "/open/ksheet" in response.url:
            open_responses.append(response)

    page.on("response", remember)
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.locator("input.edit-box").wait_for(state="visible", timeout=45_000)
    page.wait_for_timeout(8_000)

    name_box = page.locator("input.edit-box")
    name_box.fill("A1")
    name_box.press("Enter")
    page.wait_for_timeout(500)

    print("PAGE", safe_path(page.url), page.title())
    print("SHEETS", page.locator('[role="option"]').all_inner_texts())
    print("INPUTS", page.locator("input").evaluate_all(
        "els => els.map(e => ({className:e.className, value:e.value, placeholder:e.placeholder}))"
    ))
    print("EDITABLE", page.locator('[contenteditable="true"]').evaluate_all(
        "els => els.map(e => ({className:e.className, text:e.innerText})).filter(x => x.text)"
    ))
    if open_responses:
        payload = open_responses[-1].body()
        print("OPEN_PAYLOAD", {
            "length": len(payload),
            "first_32_hex": payload[:32].hex(),
            "starts_zip": payload.startswith(b"PK"),
            "starts_gzip": payload.startswith(b"\x1f\x8b"),
            "starts_json": payload.lstrip().startswith((b"{", b"[")),
            "headers": {
                key: value for key, value in open_responses[-1].headers.items()
                if key.lower() in {"content-encoding", "content-length", "content-type"}
            },
        })
    else:
        print("OPEN_PAYLOAD", "not found")
    print("RESPONSES")
    for path, (status, content_type) in sorted(responses.items()):
        print(status, content_type or "-", path)
    browser.close()
