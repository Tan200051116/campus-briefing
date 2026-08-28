(() => {
  const API_KEY = "campus-briefing-api-url";
  const DEFAULT_API_URL = "https://38-47-121-34.sslip.io";
  const READ_KEY = "campus-briefing-read-event-ids-v1";
  const MINE_KEY = "campus-briefing-mine-event-ids-v1";
  const MINE_META_KEY = "campus-briefing-mine-meta-v1";
  const NOTIFICATION_KEY = "campus-briefing-notifications-enabled-v1";
  const KNOWN_EVENTS_KEY = "campus-briefing-known-event-ids-v1";
  const params = new URLSearchParams(location.search);
  const view = ["all", "new", "mine"].includes(params.get("view")) ? params.get("view") : "all";
  const titles = { all: "全部宣讲", new: "新增通知", mine: "我的宣讲" };

  const pageTitle = document.querySelector("#page-title");
  const message = document.querySelector("#message");
  const list = document.querySelector("#event-list");
  const settings = document.querySelector("#settings-panel");
  const apiInput = document.querySelector("#api-url");
  const notificationToggle = document.querySelector("#notification-toggle");
  const keywordFilter = document.querySelector("#keyword-filter");
  const dateFilter = document.querySelector("#date-filter");
  const timeFilter = document.querySelector("#time-filter");
  const locationFilter = document.querySelector("#location-filter");
  const filterSummary = document.querySelector("#filter-summary");

  let currentEvents = [];
  let currentLastSuccess = null;
  let lastLoadedAt = 0;

  pageTitle.textContent = titles[view];
  document.title = `${titles[view]} · 宣讲工作台`;
  document.querySelector(`.stats a[href$="view=${view}"]`)?.setAttribute("aria-current", "page");

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const normalizeSearch = (value) => String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/\s+/g, "");

  const getApiUrl = () => (localStorage.getItem(API_KEY) || DEFAULT_API_URL).replace(/\/+$/, "");

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

  function getMineMeta() {
    try {
      const value = JSON.parse(localStorage.getItem(MINE_META_KEY) || "{}");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch {
      return {};
    }
  }

  const saveMineMeta = (value) => localStorage.setItem(MINE_META_KEY, JSON.stringify(value));

  function showSettings(force = false) {
    settings.hidden = force ? false : !settings.hidden;
    apiInput.value = getApiUrl();
    notificationToggle.checked = localStorage.getItem(NOTIFICATION_KEY) === "true";
    if (!settings.hidden) apiInput.focus();
  }

  function eventDateKey(event) {
    const raw = String(event.date || event.datetime || event.time || "");
    const match = raw.match(/(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})/);
    if (!match) return "";
    return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
  }

  function eventTimePeriod(event) {
    const raw = String(event.datetime || event.time || "");
    const match = raw.match(/(?:^|\s)(\d{1,2}):\d{2}/);
    if (!match) return "";
    const hour = Number(match[1]);
    if (hour < 12) return "morning";
    if (hour < 18) return "afternoon";
    return "evening";
  }

  function hasActiveFilters() {
    return Boolean(keywordFilter.value.trim() || dateFilter.value || timeFilter.value || locationFilter.value);
  }

  function matchesFilters(event) {
    const keyword = normalizeSearch(keywordFilter.value);
    if (keyword) {
      const searchable = normalizeSearch([
        event.company,
        event.title,
        event.location,
        event.datetime,
        event.time,
      ].filter(Boolean).join(" "));
      if (!searchable.includes(keyword)) return false;
    }
    if (dateFilter.value && eventDateKey(event) !== dateFilter.value) return false;
    if (timeFilter.value && eventTimePeriod(event) !== timeFilter.value) return false;
    if (locationFilter.value && String(event.location || "").trim() !== locationFilter.value) return false;
    return true;
  }

  function updateLocationOptions(events) {
    const selected = locationFilter.value;
    const locations = [...new Set(events.map((event) => String(event.location || "").trim()).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "zh-CN"));
    locationFilter.innerHTML = '<option value="">全部地点</option>'
      + locations.map((location) => `<option value="${escapeHtml(location)}">${escapeHtml(location)}</option>`).join("");
    if (locations.includes(selected)) locationFilter.value = selected;
  }

  function minePanel(event, meta) {
    if (view !== "mine") return "";
    const id = escapeHtml(event.id);
    const eventMeta = meta[String(event.id)] || {};
    const contacted = Boolean(eventMeta.contacted);
    return `
      <section class="mine-workspace" aria-label="宣讲跟进">
        <div class="mine-workspace-head">
          <label class="contact-toggle">
            <input type="checkbox" data-contacted-id="${id}"${contacted ? " checked" : ""} />
            <span>${contacted ? "已联系企业" : "尚未联系"}</span>
          </label>
          <a class="workbench-button" href="./?briefing=${encodeURIComponent(String(event.id))}">去工作台生成短信</a>
        </div>
        <label class="note-field">
          <span>我的备注</span>
          <textarea data-note-id="${id}" rows="2" placeholder="记录联系人、回访情况或现场安排…">${escapeHtml(eventMeta.note || "")}</textarea>
        </label>
      </section>`;
  }

  function eventCard(event, readIds, mineIds, meta) {
    const unread = isUnread(event, readIds);
    const mine = isMine(event, mineIds);
    const contacted = Boolean(meta[String(event.id)]?.contacted);
    const badges = [
      unread ? '<span class="badge new"><span class="unread-dot"></span>新增未读</span>' : "",
      mine ? '<span class="badge mine">我的</span>' : "",
      mine && contacted ? '<span class="badge contacted">已联系</span>' : "",
      `<span class="badge">${escapeHtml(event.kind || event.source_label || "宣讲")}</span>`,
    ].join("");
    const officialLink = event.official_url
      ? `<a class="event-link" href="${escapeHtml(event.official_url)}" target="_blank" rel="noreferrer">官网详情</a>`
      : "";
    const readButton = unread
      ? `<button class="read-button" type="button" data-read-id="${escapeHtml(event.id)}">标为已读</button>`
      : "";
    const mineButton = mine
      ? `<button class="mine-button remove" type="button" data-mine-id="${escapeHtml(event.id)}" data-mine-action="remove">移出我的</button>`
      : `<button class="mine-button" type="button" data-mine-id="${escapeHtml(event.id)}" data-mine-action="add">添加到我的</button>`;

    return `
      <article class="event-card${unread ? " unread" : ""}${mine ? " selected-mine" : ""}">
        <div class="event-top">
          <h2>${escapeHtml(event.title || event.company)}</h2>
          <div class="badges">${badges}</div>
        </div>
        <div class="event-meta">
          <p><strong>时间</strong><span>${escapeHtml(event.datetime || event.time || "待定")}</span></p>
          <p><strong>地点</strong><span>${escapeHtml(event.location || "待定")}</span></p>
        </div>
        <div class="event-actions">
          ${officialLink}
          <div class="action-buttons">${readButton}${mineButton}</div>
        </div>
        ${minePanel(event, meta)}
      </article>`;
  }

  function eventsForView(events, readIds, mineIds) {
    if (view === "new") return events.filter((event) => isUnread(event, readIds));
    if (view === "mine") return events.filter((event) => isMine(event, mineIds));
    return events;
  }

  function render() {
    const readIds = getReadIds();
    const mineIds = getMineIds();
    const meta = getMineMeta();
    const unreadCount = currentEvents.filter((event) => isUnread(event, readIds)).length;
    const mineCount = currentEvents.filter((event) => isMine(event, mineIds)).length;
    const baseSelected = eventsForView(currentEvents, readIds, mineIds);
    const selected = baseSelected.filter(matchesFilters);

    document.querySelector("#count-all").textContent = currentEvents.length;
    document.querySelector("#count-new").textContent = unreadCount;
    document.querySelector("#count-mine").textContent = mineCount;
    document.querySelector("#sync-summary").textContent = currentLastSuccess
      ? `最近同步：${new Date(currentLastSuccess).toLocaleString("zh-CN")}`
      : "尚未完成首次同步";

    filterSummary.hidden = !hasActiveFilters();
    filterSummary.textContent = hasActiveFilters() ? `筛选到 ${selected.length} 场，共 ${baseSelected.length} 场` : "";

    if (!selected.length) {
      message.hidden = false;
      message.className = "message";
      message.textContent = hasActiveFilters()
        ? "没有符合当前筛选条件的宣讲。"
        : view === "new"
          ? "没有未读的新增宣讲。"
          : view === "mine"
            ? "还没有添加宣讲，请从“全部宣讲”或“新增通知”中添加。"
            : "当前没有符合条件的宣讲。";
      list.innerHTML = "";
      return;
    }
    message.hidden = true;
    list.innerHTML = selected.map((event) => eventCard(event, readIds, mineIds, meta)).join("");
  }

  function updateKnownEvents(events) {
    const currentIds = new Set(events.map((event) => String(event.id)));
    const hasBaseline = localStorage.getItem(KNOWN_EVENTS_KEY) !== null;
    const knownIds = getStoredIds(KNOWN_EVENTS_KEY);
    const added = hasBaseline ? events.filter((event) => !knownIds.has(String(event.id))) : [];
    saveStoredIds(KNOWN_EVENTS_KEY, currentIds);

    if (!added.length || localStorage.getItem(NOTIFICATION_KEY) !== "true") return;
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const names = added.slice(0, 3).map((event) => event.company || event.title).filter(Boolean);
    const suffix = added.length > 3 ? ` 等 ${added.length} 场` : "";
    const notification = new Notification(`发现 ${added.length} 场新增宣讲`, {
      body: `${names.join("、")}${suffix}`,
      tag: "campus-briefing-new-events",
      icon: "./favicon.svg",
    });
    notification.onclick = () => {
      window.focus();
      location.href = "./events.html?view=new";
      notification.close();
    };
  }

  async function load({ silent = false } = {}) {
    const api = getApiUrl();
    if (!api) {
      message.className = "message";
      message.textContent = "请先填写 VPS API 地址。";
      showSettings(true);
      return;
    }

    if (!silent) {
      message.hidden = false;
      message.className = "message";
      message.textContent = "正在加载…";
      list.innerHTML = "";
    }

    try {
      const response = await fetch(`${api}/api/events?scope=all`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const events = Array.isArray(data.events) ? data.events : [];
      updateKnownEvents(events);
      currentEvents = events;
      currentLastSuccess = data.last_success;
      lastLoadedAt = Date.now();
      updateLocationOptions(currentEvents);
      render();
    } catch (error) {
      if (silent && currentEvents.length) return;
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

  notificationToggle.addEventListener("change", async () => {
    if (!notificationToggle.checked) {
      localStorage.setItem(NOTIFICATION_KEY, "false");
      return;
    }
    if (!("Notification" in window)) {
      notificationToggle.checked = false;
      localStorage.setItem(NOTIFICATION_KEY, "false");
      message.hidden = false;
      message.className = "message error";
      message.textContent = "当前浏览器不支持通知。iPhone 请先把工作台添加到主屏幕。";
      return;
    }
    const permission = await Notification.requestPermission();
    const enabled = permission === "granted";
    notificationToggle.checked = enabled;
    localStorage.setItem(NOTIFICATION_KEY, String(enabled));
    if (!enabled) {
      message.hidden = false;
      message.className = "message error";
      message.textContent = "通知权限未开启，可以稍后在浏览器的网站设置中重新允许。";
    }
  });

  [keywordFilter, dateFilter, timeFilter, locationFilter].forEach((control) => {
    control.addEventListener(control === keywordFilter ? "input" : "change", render);
  });
  document.querySelector("#reset-filters").addEventListener("click", () => {
    keywordFilter.value = "";
    dateFilter.value = "";
    timeFilter.value = "";
    locationFilter.value = "";
    render();
  });

  list.addEventListener("click", (clickEvent) => {
    const readButton = clickEvent.target.closest("[data-read-id]");
    if (readButton) {
      const ids = getReadIds();
      ids.add(String(readButton.dataset.readId));
      saveStoredIds(READ_KEY, ids);
      render();
      return;
    }

    const mineButton = clickEvent.target.closest("[data-mine-id]");
    if (!mineButton) return;
    const ids = getMineIds();
    const id = String(mineButton.dataset.mineId);
    if (mineButton.dataset.mineAction === "remove") ids.delete(id);
    else ids.add(id);
    saveStoredIds(MINE_KEY, ids);
    render();
  });

  list.addEventListener("change", (changeEvent) => {
    const checkbox = changeEvent.target.closest("[data-contacted-id]");
    if (!checkbox) return;
    const meta = getMineMeta();
    const id = String(checkbox.dataset.contactedId);
    meta[id] = { ...meta[id], contacted: checkbox.checked };
    saveMineMeta(meta);
    render();
  });

  list.addEventListener("input", (inputEvent) => {
    const note = inputEvent.target.closest("[data-note-id]");
    if (!note) return;
    const meta = getMineMeta();
    const id = String(note.dataset.noteId);
    meta[id] = { ...meta[id], note: note.value };
    saveMineMeta(meta);
  });

  window.addEventListener("focus", () => {
    if (Date.now() - lastLoadedAt > 5 * 60 * 1000) load({ silent: true });
  });
  window.setInterval(() => load({ silent: true }), 5 * 60 * 1000);

  apiInput.value = getApiUrl();
  notificationToggle.checked = localStorage.getItem(NOTIFICATION_KEY) === "true";
  settings.hidden = true;
  load();
})();
