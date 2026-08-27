(() => {
  const API_KEY = "campus-briefing-api-url";
  const view = ["all", "new", "mine"].includes(new URLSearchParams(location.search).get("view"))
    ? new URLSearchParams(location.search).get("view")
    : "all";
  const titles = { all: "全部宣讲", new: "新增宣讲", mine: "我的宣讲" };
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

  function showSettings(force = false) {
    settings.hidden = force ? false : !settings.hidden;
    apiInput.value = getApiUrl();
    if (!settings.hidden) apiInput.focus();
  }

  function eventCard(event) {
    const badges = [
      event.is_new ? '<span class="badge new">新增</span>' : "",
      event.is_mine ? '<span class="badge mine">我的</span>' : "",
      `<span class="badge">${escapeHtml(event.kind || event.source_label || "宣讲")}</span>`,
    ].join("");
    const assignment = event.leader || event.members
      ? `<p><strong>分组：</strong>${escapeHtml(event.leader || "未填")} / ${escapeHtml(event.members || "未填")}</p>`
      : "";
    const officialLink = event.official_url
      ? `<a class="event-link" href="${escapeHtml(event.official_url)}" target="_blank" rel="noreferrer">查看官网详情 →</a>`
      : "";

    return `
      <article class="event-card">
        <div class="event-top">
          <h2>${escapeHtml(event.title || event.company)}</h2>
          <div class="badges">${badges}</div>
        </div>
        <div class="event-meta">
          <p><strong>时间：</strong>${escapeHtml(event.datetime || event.time || "待定")}</p>
          <p><strong>地点：</strong>${escapeHtml(event.location || "待定")}</p>
          ${assignment}
          ${event.sheet ? `<p><strong>表格：</strong>${escapeHtml(event.sheet)}</p>` : ""}
        </div>
        ${officialLink}
      </article>`;
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
      const response = await fetch(`${api}/api/events?scope=${view}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      document.querySelector("#count-all").textContent = data.counts.all;
      document.querySelector("#count-new").textContent = data.counts.new;
      document.querySelector("#count-mine").textContent = data.counts.mine;
      document.querySelector("#sync-summary").textContent = data.last_success
        ? `最近同步：${new Date(data.last_success).toLocaleString("zh-CN")}`
        : "尚未完成首次同步";

      if (!data.events.length) {
        message.textContent = "当前没有符合条件的宣讲。";
        return;
      }
      message.hidden = true;
      list.innerHTML = data.events.map(eventCard).join("");
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

  load();
})();
