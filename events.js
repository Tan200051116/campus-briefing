(() => {
  const API_KEY = "campus-briefing-api-url";
  const READ_KEY = "campus-briefing-read-event-ids-v1";
  const MINE_KEY = "campus-briefing-mine-event-ids-v1";
  const view = ["all", "new", "mine"].includes(new URLSearchParams(location.search).get("view"))
    ? new URLSearchParams(location.search).get("view")
    : "all";
  const titles = { all: "全部宣讲", new: "新增通知", mine: "我的宣讲" };
  const pageTitle = document.querySelector("#page-title");
  const message = document.querySelector("#message");
  const list = document.querySelector("#event-list");
  const settings = document.querySelector("#settings-panel");
  const apiInput = document.querySelector("#api-url");

  pageTitle.textContent = titles[view];
  document.title = `${titles[view]} · 宣讲工作台`;
  document.querySelector(`.stats a[href$="view=${view}"]`)?.setAttribute("aria-current", "page");

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const getApiUrl = () => (localStorage.getItem(API_KEY) || "").replace(/\/+$/, "");

  const getStoredIds = (key) => {
    try {
      const value = JSON.parse(localStorage.getItem(key) || "[]");
      return new Set(Array.isArray(value) ? value.map(String) : []);
    } catch {
      return new Set();
    }
  };

  const saveStoredIds = (key, ids) => localStorage.setItem(key, JSON.stringify([...ids]));
  const getReadIds = () => getStoredIds(READ_KEY);
  const getMineIds = () => getStoredIds(MINE_KEY);
  const isUnread = (event, readIds) => !readIds.has(String(event.id));
  const isMine = (event, mineIds) => mineIds.has(String(event.id));

  function showSettings(force = false) {
    settings.hidden = force ? false : !settings.hidden;
    apiInput.value = getApiUrl();
    if (!settings.hidden) apiInput.focus();
  }

  function eventCard(event, readIds, mineIds) {
    const unread = isUnread(event, readIds);
    const mine = isMine(event, mineIds);
    const badges = [
      unread ? '<span class="badge new"><span class="unread-dot"></span>新增未读</span>' : "",
      mine ? '<span class="badge mine">我的</span>' : "",
      `<span class="badge">${escapeHtml(event.kind || event.source_label || "宣讲")}</span>`,
    ].join("");
    const officialLink = event.official_url
      ? `<a class="event-link" href="${escapeHtml(event.official_url)}" target="_blank" rel="noreferrer">查看官网详情 →</a>`
      : "";
    const readButton = unread
      ? `<button class="read-button" type="button" data-read-id="${escapeHtml(event.id)}">标为已读</button>`
      : "";
    const mineButton = mine
      ? `<button class="mine-button remove" type="button" data-mine-id="${escapeHtml(event.id)}" data-mine-action="remove">移出我的宣讲</button>`
      : `<button class="mine-button" type="button" data-mine-id="${escapeHtml(event.id)}" data-mine-action="add">＋ 添加到我的宣讲</button>`;

    return `
      <article class="event-card${unread ? " unread" : ""}${mine ? " selected-mine" : ""}">
        <div class="event-top">
          <h2>${escapeHtml(event.title || event.company)}</h2>
          <div class="badges">${badges}</div>
        </div>
        <div class="event-meta">
          <p><strong>时间：</strong>${escapeHtml(event.datetime || event.time || "待定")}</p>
          <p><strong>地点：</strong>${escapeHtml(event.location || "待定")}</p>
        </div>
        <div class="event-actions">
          ${officialLink}
          <div class="action-buttons">${readButton}${mineButton}</div>
        </div>
      </article>`;
  }

  function render(events, lastSuccess) {
    const readIds = getReadIds();
    const mineIds = getMineIds();
    const unreadCount = events.filter((event) => isUnread(event, readIds)).length;
    const mineCount = events.filter((event) => isMine(event, mineIds)).length;
    const selected = view === "new"
      ? events.filter((event) => isUnread(event, readIds))
      : view === "mine"
        ? events.filter((event) => isMine(event, mineIds))
        : events;

    document.querySelector("#count-all").textContent = events.length;
    document.querySelector("#count-new").textContent = unreadCount;
    document.querySelector("#count-mine").textContent = mineCount;
    document.querySelector("#sync-summary").textContent = lastSuccess
      ? `最近同步：${new Date(lastSuccess).toLocaleString("zh-CN")}`
      : "尚未完成首次同步";

    if (!selected.length) {
      message.hidden = false;
      message.className = "message";
      message.textContent = view === "new"
        ? "没有未读的新增宣讲。"
        : view === "mine"
          ? "还没有添加宣讲，请从“全部宣讲”或“新增通知”中添加。"
          : "当前没有符合条件的宣讲。";
      list.innerHTML = "";
      return;
    }
    message.hidden = true;
    list.innerHTML = selected.map((event) => eventCard(event, readIds, mineIds)).join("");
  }

  async function load() {
    const api = getApiUrl();
    if (!api) {
      message.className = "message";
      message.textContent = "请先填写 VPS API 地址。";
      showSettings(true);
      return;
    }

    message.hidden = false;
    message.className = "message";
    message.textContent = "正在加载…";
    list.innerHTML = "";

    try {
      const response = await fetch(`${api}/api/events?scope=all`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      render(data.events, data.last_success);
    } catch (error) {
      message.hidden = false;
      message.className = "message error";
      message.textContent = `连接失败：${error.message}。请检查 VPS 地址、HTTPS 和服务状态。`;
    }
  }

  document.querySelector("#settings-button").addEventListener("click", () => showSettings());
  document.querySelector("#save-settings").addEventListener("click", () => {
    const value = apiInput.value.trim().replace(/\/+$/, "");
    if (!/^https:\/\//i.test(value)) {
      message.hidden = false;
      message.className = "message error";
      message.textContent = "API 地址必须以 https:// 开头。";
      return;
    }
    localStorage.setItem(API_KEY, value);
    settings.hidden = true;
    load();
  });

  list.addEventListener("click", (event) => {
    const readButton = event.target.closest("[data-read-id]");
    if (readButton) {
      const ids = getReadIds();
      ids.add(String(readButton.dataset.readId));
      saveStoredIds(READ_KEY, ids);
      load();
      return;
    }

    const mineButton = event.target.closest("[data-mine-id]");
    if (!mineButton) return;
    const ids = getMineIds();
    const id = String(mineButton.dataset.mineId);
    if (mineButton.dataset.mineAction === "remove") ids.delete(id);
    else ids.add(id);
    saveStoredIds(MINE_KEY, ids);
    load();
  });

  load();
})();
