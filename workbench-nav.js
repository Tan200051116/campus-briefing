(() => {
  if (document.querySelector(".workbench-quick-nav")) return;

  const currentView = new URLSearchParams(location.search).get("view") || "workbench";
  const items = [
    ["workbench", "工作台", "./"],
    ["all", "全部宣讲", "./events.html?view=all"],
    ["new", "新增通知", "./events.html?view=new"],
    ["mine", "我的宣讲", "./events.html?view=mine"],
  ];

  const nav = document.createElement("nav");
  nav.className = "workbench-quick-nav";
  nav.setAttribute("aria-label", "宣讲工作台导航");
  nav.innerHTML = items
    .map(([id, label, href]) => {
      const active = id === currentView ? ' aria-current="page"' : "";
      return `<a href="${href}"${active}>${label}</a>`;
    })
    .join("");

  document.body.appendChild(nav);
  document.body.classList.add("has-workbench-quick-nav");
})();
