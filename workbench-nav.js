(() => {
  if (document.querySelector(".workbench-quick-nav")) return;

  const params = new URLSearchParams(location.search);
  const isEventsPage = /events\.html$/.test(location.pathname);
  const currentView = params.get("view") || (isEventsPage ? "all" : "workbench");
  const icons = {
    workbench: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/></svg>',
    all: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z"/></svg>',
    new: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/></svg>',
    mine: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18l-6-4-6 4Z"/></svg>',
  };
  const items = [
    ["workbench", "工作台", "./"],
    ["all", "全部", "./events.html?view=all"],
    ["new", "新增", "./events.html?view=new"],
    ["mine", "我的", "./events.html?view=mine"],
  ];

  const nav = document.createElement("nav");
  nav.className = "workbench-quick-nav";
  nav.setAttribute("aria-label", "宣讲工作台导航");
  nav.innerHTML = `
    <a class="workbench-nav-brand" href="./" aria-label="返回宣讲工作台">
      <span class="brand-mark">宣</span>
      <span><strong>宣讲工作台</strong><small>Campus Briefing</small></span>
    </a>
    <div class="workbench-nav-items">
      ${items.map(([id, label, href]) => {
        const active = id === currentView ? ' aria-current="page"' : "";
        return `<a href="${href}"${active}>${icons[id]}<span>${label}</span></a>`;
      }).join("")}
    </div>`;

  document.body.prepend(nav);
  document.body.classList.add("has-workbench-quick-nav");
  if (isEventsPage) document.body.classList.add("workbench-events-page");
})();
