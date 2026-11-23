/* Interface behaviour shared by every page: dropdowns, toasts, the bell panel and the search
   palette. The palette reads one small index (dashboard:search_index) once and filters it in
   the browser, so it also works in the static demo. */
  // One dropdown for every list: the native select stays in the form (hidden) and is driven
  // by a button and a listbox in the site's own style. Keyboard: Enter/Space, arrows, Esc.
  (function () {
    const chev = '<svg class="icon chev" aria-hidden="true"><use href="#i-chev"/></svg>';
    document.querySelectorAll("select.input").forEach((select, n) => {
      const box = document.createElement("div");
      box.className = "dd";
      select.parentNode.insertBefore(box, select);
      box.appendChild(select);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "input dd-btn";
      button.setAttribute("aria-haspopup", "listbox");
      button.setAttribute("aria-expanded", "false");
      if (select.getAttribute("aria-label")) button.setAttribute("aria-label", select.getAttribute("aria-label"));
      if (select.id) { button.id = select.id; select.removeAttribute("id"); }
      const list = document.createElement("ul");
      list.className = "dd-list";
      list.setAttribute("role", "listbox");
      list.id = "dd-list-" + n;
      button.setAttribute("aria-controls", list.id);
      [...select.options].forEach((option, i) => {
        const item = document.createElement("li");
        item.setAttribute("role", "option");
        item.textContent = option.textContent;
        item.dataset.index = i;
        list.appendChild(item);
      });
      box.append(button, list);
      let active = select.selectedIndex;
      const items = [...list.children];
      button.innerHTML = "<span></span>" + chev;  // built once: re-rendering inside a click detached its target
      const label = button.firstChild;
      function render() {
        label.textContent = select.options[select.selectedIndex]?.textContent || "";
        box.toggleAttribute("data-empty", !select.value);
        items.forEach((item, i) => {
          item.setAttribute("aria-selected", String(i === select.selectedIndex));
          item.toggleAttribute("data-active", i === active);
        });
      }
      function open(state) {
        box.toggleAttribute("data-open", state);
        button.setAttribute("aria-expanded", String(state));
        if (state) { active = select.selectedIndex; render(); items[active]?.scrollIntoView({ block: "nearest" }); }
      }
      function choose(i) {
        select.selectedIndex = i;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        open(false); render(); button.focus();
      }
      button.addEventListener("click", () => open(!box.hasAttribute("data-open")));
      list.addEventListener("click", (event) => { const item = event.target.closest("li"); if (item) choose(Number(item.dataset.index)); });
      button.addEventListener("keydown", (event) => {
        const isOpen = box.hasAttribute("data-open");
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          if (!isOpen) return open(true);
          active = Math.max(0, Math.min(items.length - 1, active + (event.key === "ArrowDown" ? 1 : -1)));
          render(); items[active].scrollIntoView({ block: "nearest" });
        } else if ((event.key === "Enter" || event.key === " ") && isOpen) { event.preventDefault(); choose(active); }
        else if (event.key === "Escape" && isOpen) { event.preventDefault(); open(false); }
      });
      document.addEventListener("click", (event) => { if (event.target.isConnected && !box.contains(event.target)) open(false); });
      render();
    });
  })();

(function () {
  const box = document.querySelector("[data-toasts]");
  if (!box) return;
  const hide = () => box.setAttribute("data-hidden", "");
  box.addEventListener("click", (event) => { if (event.target.closest("[data-close]")) hide(); });
  setTimeout(hide, 7000);
})();

// Pop-up panels under a header button (bell, account): one open at a time, Esc and a click
// outside close them.
(function () {
  const pairs = [...document.querySelectorAll("[data-pop]")].map((button) => [button, button.parentNode.querySelector("[data-pop-panel]")]);
  const set = (pair, on) => { pair[1].toggleAttribute("data-open", on); pair[0].setAttribute("aria-expanded", String(on)); };
  pairs.forEach((pair) => pair[0].addEventListener("click", (event) => {
    event.stopPropagation();
    const on = !pair[1].hasAttribute("data-open");
    pairs.forEach((other) => set(other, other === pair && on));
  }));
  document.addEventListener("click", (event) => pairs.forEach((pair) => { if (!pair[1].contains(event.target)) set(pair, false); }));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") pairs.forEach((pair) => set(pair, false)); });
})();

// The upload window: any [data-upload-open] button opens it (a card passes data-case), and so
// does the address #upload (the search palette's suggestion). The file is checked here by
// type and size before it is sent; the server checks it again.
(function () {
  const form = document.querySelector("[data-upload]");
  if (!form) return;
  const scrim = document.querySelector("[data-upload-scrim]");
  const input = form.querySelector("[data-file]");
  const drop = form.querySelector("[data-drop]");
  const row = form.querySelector("[data-file-row]");
  const error = form.querySelector("[data-file-error]");
  const submit = form.querySelector("[data-upload-submit]");
  const caseField = form.querySelector('[name="case"]');
  const TYPES = /\.(pdf|docx|xlsx|jpe?g|png|tiff?)$/i, MAX = 5 * 1024 * 1024;
  const size = (bytes) => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
  function show() {
    const file = input.files[0];
    let problem = "";
    if (file && !TYPES.test(file.name)) problem = "Этот формат не принимается: нужен PDF, DOCX, XLSX, JPG, PNG или TIFF.";
    else if (file && file.size > MAX) problem = "Файл больше 5 МБ.";
    error.textContent = problem; error.hidden = !problem;
    row.hidden = !file || !!problem;
    drop.toggleAttribute("data-filled", !!file && !problem);
    if (file && !problem) { form.querySelector("[data-file-name]").textContent = file.name; form.querySelector("[data-file-size]").textContent = size(file.size); }
    submit.disabled = !file || !!problem;
  }
  function open(caseId) {
    caseField.value = caseId || "";
    form.setAttribute("data-open", ""); scrim.setAttribute("data-open", "");
    document.documentElement.style.overflow = "hidden";
    form.focus();
  }
  function close() {
    form.removeAttribute("data-open"); scrim.removeAttribute("data-open");
    document.documentElement.style.overflow = "";
    if (location.hash === "#upload") history.replaceState(null, "", location.pathname + location.search);
  }
  document.querySelectorAll("[data-upload-open]").forEach((button) => button.addEventListener("click", () => open(button.dataset.case)));
  form.querySelector("[data-upload-close]").addEventListener("click", close);
  scrim.addEventListener("click", close);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && form.hasAttribute("data-open") && !form.querySelector(".dd[data-open]")) close(); });
  input.addEventListener("change", show);
  form.querySelector("[data-file-clear]").addEventListener("click", (event) => { event.preventDefault(); input.value = ""; show(); });
  ["dragenter", "dragover"].forEach((type) => drop.addEventListener(type, (event) => { event.preventDefault(); drop.setAttribute("data-over", ""); }));
  ["dragleave", "drop"].forEach((type) => drop.addEventListener(type, () => drop.removeAttribute("data-over")));
  drop.addEventListener("drop", (event) => { event.preventDefault(); if (event.dataTransfer.files.length) { input.files = event.dataTransfer.files; show(); } });
  form.addEventListener("submit", () => { submit.disabled = true; submit.textContent = "загружаем…"; });
  const fromHash = () => { if (location.hash === "#upload") { document.querySelector("[data-palette]")?.removeAttribute("data-open"); document.querySelector("[data-scrim]")?.removeAttribute("data-open"); open(document.querySelector("[data-upload-open][data-case]")?.dataset.case); } };
  window.addEventListener("hashchange", fromHash); fromHash();
})();

(function () {
  const palette = document.querySelector("[data-palette]");
  if (!palette) return;
  const scrim = document.querySelector("[data-scrim]");
  const input = palette.querySelector("input");
  const body = palette.querySelector("[data-results]");
  const tabs = [...palette.querySelectorAll("[data-tab]")];
  let index = null, tab = "all", active = 0;
  const GROUPS = { object: "объекты", document: "документы", event: "события" };
  const esc = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  async function load() {
    if (index) return index;
    const response = await fetch(palette.dataset.index, { credentials: "same-origin" });
    index = response.ok ? await response.json() : { items: [], actions: [] };
    return index;
  }
  function render() {
    const query = input.value.trim().toLowerCase();
    const words = query.split(/\s+/).filter(Boolean);
    const items = index.items.filter((item) => (tab === "all" || item.group === tab) && words.every((word) => item.search.includes(word)));
    let html = "", n = 0;
    for (const group of Object.keys(GROUPS)) {
      const part = items.filter((item) => item.group === group).slice(0, query ? 8 : 4);
      if (!part.length) continue;
      html += `<div class="palette-group">${GROUPS[group]}</div>`;
      for (const item of part) html += `<a class="palette-item" href="${esc(item.url)}" data-i="${n++}"><span>${esc(item.title)}</span><small>${esc(item.note || "открыть")}</small></a>`;
    }
    if (!query && tab === "all" && index.actions.length) {
      html += `<div class="palette-group">предложения</div>`;
      for (const action of index.actions) html += `<a class="palette-item" href="${esc(action.url)}" data-i="${n++}"><span>+&nbsp; ${esc(action.title)}</span><small></small></a>`;
    }
    body.innerHTML = html || `<div class="palette-group">ничего не найдено</div>`;
    active = 0; mark();
  }
  function mark() { body.querySelectorAll("[data-i]").forEach((el) => el.toggleAttribute("data-active", Number(el.dataset.i) === active)); }
  async function open() {
    palette.setAttribute("data-open", ""); scrim.setAttribute("data-open", "");
    input.focus(); await load(); render();
  }
  function close() { palette.removeAttribute("data-open"); scrim.removeAttribute("data-open"); }
  document.querySelectorAll("[data-search-open]").forEach((el) => el.addEventListener("click", open));
  scrim.addEventListener("click", close);
  input.addEventListener("input", () => index && render());
  tabs.forEach((button) => button.addEventListener("click", () => {
    tab = button.dataset.tab;
    tabs.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    render(); input.focus();
  }));
  document.addEventListener("keydown", (event) => {
    const isOpen = palette.hasAttribute("data-open");
    if ((event.key === "k" && (event.metaKey || event.ctrlKey)) || (event.key === "/" && !isOpen && !/input|textarea|select/i.test(document.activeElement.tagName))) { event.preventDefault(); open(); return; }
    if (!isOpen) return;
    const links = body.querySelectorAll("[data-i]");
    if (event.key === "Escape") close();
    else if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); active = Math.max(0, Math.min(links.length - 1, active + (event.key === "ArrowDown" ? 1 : -1))); mark(); links[active]?.scrollIntoView({ block: "nearest" }); }
    else if (event.key === "Enter" && links[active]) { event.preventDefault(); location.href = links[active].href; }
  });
})();
