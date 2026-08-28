(() => {
  const API_KEY = "campus-briefing-api-url";
  const READ_KEY = "campus-briefing-read-event-ids-v1";
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

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const getApiUrl = () => (localStorage.getItem(API_KEY) || "").replace(/\/+$/, "");

  const getReadIds = () => {
    try {
      const value = JSON.parse(localStorage.getItem(READ_KEY) || "[]");
      return new Set(Array.isArray(value) ? value.map(String) : []);
    } catch {
      return new Set();
    }
  };

  const saveReadIds = (ids) => localStorage.setItem(READ_KEY, JSON.stringify([...ids]));
  const isUnread = (event, readIds) => Boolean(event.is_new) && !readIds.has(String(event.id));

  function showSettings(force = false) {
    settings.hidden = force ? false : !settings.hidden;
    apiInput.value = getApiUrl();
    if (!settings.hidden) apiInput.focus();
  }

  function eventCard(event, readIds) {
    const unread = isUnread(event, readIds);
    const badges = [
      unread ? '<span class="badge new"><span class="unread-dot"></span>新增未读</span>' : "",
      event.is_mine ? '<span class="badge mine">我的</span>' : "",
      `<span class="badge">${escapeHtml(event.kind || event.source_label || "宣讲")}</span>`,
    ].join("");
    const assignment = event.leader || event.members
      ? `<p><strong>分组：</strong>${escapeHtml(event.leader || "未填")} / ${escapeHtml(event.members || "未填")}</p>`
      : "";
    const officialLink = event.official_url
      ? `<a class="event-link" href="${escapeHtml(event.official_url)}" target="_blank" rel="noreferrer">查看官网详情 →</a>`
      : "";
    const readButton = unread
      ? `<button class="read-button" type="button" data-read-id="${escapeHtml(event.id)}">标为已读</button>`
      : "";
    const actions = officialLink || readButton
      ? `<div class="event-actions">${officialLink}${readButton}</div>`
      : "";

    return `
      <article class="event-card${unread ? " unread" : ""}">
        <div class="event-top">
          <h2>${escapeHtml(event.title || event.company)}</h2>
          <div class="badges">${badges}</div>
        </div>
        <div class="event-meta">
          <p><strong>时间：</strong>${escapeHtml(event.datetime || event.time || "待定")}</p>
          <p><strong>地点：</strong>${escapeHtml(event.location || "待定")}</p>
          ${assignment}
        </div>
        ${actions}
      </article>`;
  }

  function render(events, lastSuccess) {
    const readIds = getReadIds();
    const unreadCount = events.filter((event) => isUnread(event, readIds)).length;
    const mineCount = events.filter((event) => event.is_mine).length;
    const selected = view === "new"
      ? events.filter((event) => isUnread(event, readIds))
      : view === "mine"
        ? events.filter((event) => event.is_mine)
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
      message.textContent = view === "new" ? "没有未读的新增宣讲。" : "当前没有符合条件的宣讲。";
      list.innerHTML = "";
      return;
    }
    message.hidden = true;
    list.innerHTML = selected.map((event) => eventCard(event, readIds)).join("");
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
    const button = event.target.closest("[data-read-id]");
    if (!button) return;
    const ids = getReadIds();
    ids.add(String(button.dataset.readId));
    saveReadIds(ids);
    load();
  });

  load();
})();
