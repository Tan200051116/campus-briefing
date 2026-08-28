(() => {
  const API_KEY = "campus-briefing-api-url";
  const DEFAULT_API_URL = "https://38-47-121-34.sslip.io";
  const selectedBriefingId = new URLSearchParams(location.search).get("briefing");
  let events = [];
  let selectedBriefing = null;
  let replayingClick = false;

  const normalize = (value) => String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/【.*?】|\[.*?\]/g, "")
    .replace(/20\d{2}届/g, "")
    .replace(/(秋季|春季|全球|校园|应届生|毕业生|专场|空中)?(招聘|招录|宣讲会|宣讲)/g, "")
    .replace(/[^0-9a-z\u4e00-\u9fff]/g, "");

  function companyQuery(text) {
    const beforeContact = String(text || "").split(
      /(?:对接人|联系人|联系电话|电话|1[3-9]\d{9}|[\u4e00-\u9fa5·]{1,5}(?:经理|老师|先生|女士))/,
    )[0];
    return normalize(beforeContact.replace(/^(?:企业名称|企业|公司)[为是：:\s]*/, ""));
  }

  function matchEvent(text) {
    const whole = normalize(text);
    const query = companyQuery(text);
    let best = null;
    let bestScore = 0;

    for (const event of events) {
      const company = normalize(event.company || event.title);
      const base = company.replace(/(?:集团有限责任公司|股份有限公司|有限责任公司|集团有限公司|有限公司|集团|公司)$/g, "");
      const aliases = [...new Set([company, base].filter((value) => value.length >= 2))];
      for (const alias of aliases) {
        let score = 0;
        if (whole.includes(alias)) score = 1000 + alias.length;
        else if (query.length >= 2 && (alias.includes(query) || query.includes(alias))) score = 500 + Math.min(alias.length, query.length);
        if (score > bestScore) {
          best = event;
          bestScore = score;
        }
      }
    }
    return best;
  }

  function setTextareaValue(textarea, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
    setter.call(textarea, value);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function ensureHint(textarea) {
    let hint = document.querySelector("#briefing-autofill-hint");
    if (hint) return hint;
    hint = document.createElement("p");
    hint.id = "briefing-autofill-hint";
    hint.style.cssText = "margin:8px 2px 0;color:#647b86;font-size:12px;line-height:1.55";
    textarea.insertAdjacentElement("afterend", hint);
    return hint;
  }

  function updateHint(textarea) {
    const hint = ensureHint(textarea);
    if (!events.length) {
      hint.textContent = "宣讲数据尚未连接；仍可按原方式填写完整信息。";
      return;
    }
    const matched = matchEvent(textarea.value);
    hint.textContent = matched
      ? `已匹配：${matched.company || matched.title}｜${matched.datetime || "时间待定"}｜${matched.location || "地点待定"}`
      : "输入企业名称、联系人和电话，匹配成功后会自动补入官网时间地点。";
  }

  function applySelectedBriefing(textarea) {
    if (!selectedBriefing || textarea.dataset.selectedBriefingApplied === "true") return;
    if (textarea.value.trim()) return;
    const briefingText = [
      `企业名称：${selectedBriefing.company || selectedBriefing.title || ""}`,
      `宣讲时间：${selectedBriefing.datetime || selectedBriefing.time || ""}`,
      `宣讲地点：${selectedBriefing.location || ""}`,
      "联系人：",
      "联系电话：",
    ].join("\n");
    setTextareaValue(textarea, briefingText);
    textarea.dataset.selectedBriefingApplied = "true";
    updateHint(textarea);
    textarea.focus();
  }

  async function loadEvents() {
    const api = (localStorage.getItem(API_KEY) || DEFAULT_API_URL).replace(/\/+$/, "");
    if (!api) return;
    try {
      const response = await fetch(`${api}/api/events?scope=all`, { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      events = Array.isArray(payload.events) ? payload.events : [];
      selectedBriefing = selectedBriefingId
        ? events.find((event) => String(event.id) === String(selectedBriefingId)) || null
        : null;
      const textarea = document.querySelector('textarea[placeholder*="中兴通讯"]');
      if (textarea) {
        applySelectedBriefing(textarea);
        updateHint(textarea);
      }
    } catch {
      // 网络失败时保留原工作台的手动识别能力。
    }
  }

  function install() {
    const textarea = document.querySelector('textarea[placeholder*="中兴通讯"]');
    const button = [...document.querySelectorAll("button")]
      .find((item) => item.textContent.includes("识别并整理"));
    if (!textarea || !button || button.dataset.briefingAutofill === "ready") return false;

    button.dataset.briefingAutofill = "ready";
    ensureHint(textarea);
    textarea.addEventListener("input", () => updateHint(textarea));
    button.addEventListener("click", (clickEvent) => {
      if (replayingClick) return;
      const matched = matchEvent(textarea.value);
      if (!matched) return;

      clickEvent.preventDefault();
      clickEvent.stopPropagation();
      clickEvent.stopImmediatePropagation();
      const original = textarea.value.trim();
      const enriched = [
        original,
        `企业名称：${matched.company || matched.title || ""}`,
        `宣讲时间：${matched.datetime || matched.time || ""}`,
        `宣讲地点：${matched.location || ""}`,
      ].filter(Boolean).join("\n");
      setTextareaValue(textarea, enriched);
      updateHint(textarea);

      replayingClick = true;
      window.setTimeout(() => {
        button.click();
        replayingClick = false;
      }, 80);
    }, true);
    updateHint(textarea);
    applySelectedBriefing(textarea);
    return true;
  }

  const observer = new MutationObserver(() => {
    if (install()) observer.disconnect();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  install();
  loadEvents();
})();
