// Tab navigation, expansion selection, glossary search, definition tooltips and the card errata tab.
// No external dependencies, no eval and no HTML built from data (works under a strict CSP).
// The UI strings are Polish because the page is Polish.
(function () {
  "use strict";

  const panels = {
    rules: document.getElementById("rules"),
    glossary: document.getElementById("glossary"),
    cards: document.getElementById("cards"),
  };
  const tabs = document.querySelectorAll("[data-tab]");

  function show(name) {
    for (const [key, panel] of Object.entries(panels)) panel.hidden = key !== name;
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
  }

  // ---------------------------------------------------------- search
  const input = document.getElementById("search");
  const fullText = document.getElementById("search-full-text");
  const counter = document.getElementById("result-count");
  const empty = document.getElementById("no-results");
  const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
  const items = Array.from(panels.glossary.querySelectorAll(".entry, .alias")).map((el) => ({
    el,
    name: norm(el.dataset.search || ""),
    text: norm(el.textContent),
  }));
  const groups = Array.from(panels.glossary.querySelectorAll(".group"));
  const letters = Array.from(panels.glossary.querySelectorAll(".letter"));
  // entries of unselected expansions carry the class "exp-off" and never count as visible
  const SHOWN = ".entry:not([hidden]):not(.exp-off), .alias:not([hidden]):not(.exp-off)";

  function filter() {
    const q = norm(input.value.trim());
    let shown = 0;
    for (const it of items) {
      const active = !it.el.classList.contains("exp-off");
      const hit = !q || it.name.includes(q) || (fullText.checked && it.text.includes(q));
      it.el.hidden = !hit;
      if (hit && active && it.el.classList.contains("entry")) shown++;
    }
    for (const g of groups) {
      const visible = g.querySelector(SHOWN);
      const active = g.querySelector(".entry:not(.exp-off), .alias:not(.exp-off)");
      const headHit = q && active && norm(g.querySelector(".group-title").textContent).includes(q);
      if (headHit && !visible) g.querySelectorAll(".entry, .alias").forEach((el) => { el.hidden = false; });
      g.hidden = !visible && !headHit;
    }
    for (const L of letters) {
      L.hidden = !L.querySelector(SHOWN);
      const link = panels.glossary.querySelector(`.letters a[href="#${L.id}"]`);
      if (link) link.classList.toggle("off", L.hidden);
    }
    empty.hidden = letters.some((L) => !L.hidden);
    counter.textContent = q ? `Znaleziono haseł: ${shown}` : `Haseł: ${shown}`;
  }
  input.addEventListener("input", () => { filter(); window.scrollTo(0, 0); });
  fullText.addEventListener("change", filter);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { input.value = ""; filter(); }
  });

  // ---------------------------------------------------------- expansions
  // Content of an expansion carries data-req (all listed expansions must be selected) and/or
  // data-not (none of them may be selected). The selection is kept in a cookie for a year;
  // pages opened from file:// cannot keep cookies in Chrome, so there it falls back to localStorage.
  const EXP_KEY = "wop_dodatki";
  const expInputs = Array.from(document.querySelectorAll("input[data-exp]"));
  const expNames = Object.fromEntries(expInputs.map((i) => [i.dataset.exp, i.parentElement.textContent.trim()]));
  const expCount = document.getElementById("exp-count");
  const conditional = Array.from(document.querySelectorAll("[data-req], [data-not]"));
  const words = (s) => (s || "").split(" ").filter(Boolean);

  function readSelection() {
    const m = document.cookie.match(new RegExp(`(?:^|;\\s*)${EXP_KEY}=([^;]*)`));
    let raw = m ? decodeURIComponent(m[1]) : null;
    if (raw === null && location.protocol === "file:") {
      try { raw = localStorage.getItem(EXP_KEY); } catch (_) { raw = null; }
    }
    return new Set((raw || "").split(",").filter((k) => k in expNames));
  }

  function saveSelection(selected) {
    const value = Array.from(selected).join(",");
    if (location.protocol === "file:") {
      try { localStorage.setItem(EXP_KEY, value); } catch (_) { /* storage blocked: keep it for this visit only */ }
      return;
    }
    const dir = location.pathname.replace(/[^/]*$/, "");
    const secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${EXP_KEY}=${encodeURIComponent(value)}; Max-Age=31536000; Path=${dir}; SameSite=Lax${secure}`;
  }

  let selected = readSelection();
  const isOn = (el) => words(el.dataset.req).every((k) => selected.has(k)) &&
    !words(el.dataset.not).some((k) => selected.has(k));

  function applySelection() {
    expInputs.forEach((i) => { i.checked = selected.has(i.dataset.exp); });
    conditional.forEach((el) => el.classList.toggle("exp-off", !isOn(el)));
    if (expCount) expCount.textContent = selected.size ? `(${selected.size})` : "";
    filter();
  }

  expInputs.forEach((i) => i.addEventListener("change", () => {
    if (i.checked) selected.add(i.dataset.exp); else selected.delete(i.dataset.exp);
    saveSelection(selected);
    applySelection();
  }));

  // close the expansion menu on a click outside it or on Escape
  const expMenu = document.querySelector(".exp-menu");
  if (expMenu) {
    document.addEventListener("click", (ev) => { if (!expMenu.contains(ev.target)) expMenu.open = false; });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") expMenu.open = false; });
  }

  // A card can exist in several versions (e.g. replaced by an expansion); links point to the
  // first one, so switch to the version that is currently shown.
  function shownVersion(el) {
    if (!el || !el.classList.contains("card") || !el.closest(".exp-off")) return el;
    const same = document.querySelectorAll(`.card[data-name="${CSS.escape(el.dataset.name)}"]`);
    return Array.from(same).find((c) => !c.closest(".exp-off")) || el;
  }

  // notice shown when a link opens content of an unselected expansion
  const notice = document.createElement("div");
  notice.className = "exp-notice";
  notice.setAttribute("role", "status");
  notice.hidden = true;
  document.body.appendChild(notice);

  function explainHidden(el) {
    const missing = new Set();
    const blocking = new Set();
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (!n.dataset) continue;
      words(n.dataset.req).forEach((k) => { if (!selected.has(k)) missing.add(k); });
      words(n.dataset.not).forEach((k) => { if (selected.has(k)) blocking.add(k); });
    }
    const names = (set) => Array.from(set).map((k) => `„${expNames[k] || k}”`).join(", ");
    const text = document.createElement("span");
    const parts = [text];
    if (missing.size) {
      text.textContent = `Ta treść pochodzi z dodatku ${names(missing)}, który jest wyłączony.`;
      const on = document.createElement("button");
      on.type = "button";
      on.textContent = "Włącz";
      on.addEventListener("click", () => {
        missing.forEach((k) => selected.add(k));
        saveSelection(selected);
        applySelection();
        route();
      });
      parts.push(on);
    } else {
      text.textContent = `Ta treść dotyczy gry bez dodatku ${names(blocking)}.`;
    }
    const close = document.createElement("button");
    close.type = "button";
    close.className = "close";
    close.setAttribute("aria-label", "Zamknij");
    close.textContent = "×";
    close.addEventListener("click", () => { notice.hidden = true; });
    parts.push(close);
    notice.replaceChildren(...parts);
    notice.hidden = false;
  }

  // ---------------------------------------------------------- hash routing
  function route() {
    const id = decodeURIComponent(location.hash.slice(1));
    const el = shownVersion(id ? document.getElementById(id) : null);
    // the panel that holds the target element; the rules tab is the default
    const name = Object.keys(panels).find((key) => el && panels[key].contains(el)) || "rules";
    show(name);
    if (name === "glossary" && el.closest("[hidden]") && input.value) { input.value = ""; filter(); }
    if (el && el.closest(".exp-off")) explainHidden(el); else notice.hidden = true;
    if (el && !Object.values(panels).includes(el)) {
      requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
    } else {
      window.scrollTo(0, 0);
    }
  }
  window.addEventListener("hashchange", route);

  // ---------------------------------------------------------- definition tooltips
  // Mouse: hovering a term shows its definition; clicking opens the entry.
  // Touch: the first tap shows the definition with an "open entry" link;
  // a second tap on the same term (or on that link) opens the entry; a tap elsewhere closes it.
  const pop = document.createElement("div");
  pop.className = "popover";
  pop.setAttribute("role", "tooltip");
  pop.hidden = true;
  document.body.appendChild(pop);
  const hoverQuery = window.matchMedia("(hover: hover)");
  let lastPointer = "mouse";
  let popFor = null; // the term link the popover currently belongs to
  let popScrollY = 0;

  // Track the input type so touch taps on hybrid devices (touch laptops) behave like on a phone.
  document.addEventListener("pointerdown", (ev) => { lastPointer = ev.pointerType; }, { passive: true, capture: true });
  const isTouch = () => lastPointer === "touch" || !hoverQuery.matches;

  function showPop(link, withOpenLink) {
    const target = shownVersion(document.getElementById(link.getAttribute("href").slice(1)));
    const isCard = target && target.classList.contains("card");
    if (!target || !(isCard || target.classList.contains("entry"))) return false;
    const title = document.createElement("strong");
    title.textContent = target.querySelector("h3 .t").textContent;
    const body = document.createElement("div");
    // glossary entry: first paragraph of the definition; card: the corrected card text
    const def = target.querySelector(isCard ? ".card-fixed p" : ".def p");
    body.textContent = def ? def.textContent : "";
    const parts = [title, body];
    if (withOpenLink) {
      const open = document.createElement("a");
      open.className = "pop-open";
      open.href = link.getAttribute("href");
      open.textContent = isCard ? "Otwórz kartę →" : "Otwórz hasło →";
      parts.push(open);
    }
    pop.replaceChildren(...parts);
    pop.classList.toggle("touch", withOpenLink);
    pop.hidden = false;
    popFor = link;
    popScrollY = window.scrollY;
    const r = link.getBoundingClientRect();
    const w = pop.offsetWidth;
    const h = pop.offsetHeight;
    const left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
    let top = r.bottom + 8;
    if (top + h > window.innerHeight - 8) top = r.top - h - 8;
    pop.style.left = `${Math.max(8, left)}px`;
    pop.style.top = `${Math.max(8, top)}px`;
    return true;
  }
  function hidePop() { pop.hidden = true; popFor = null; }

  document.addEventListener("mouseover", (ev) => {
    if (isTouch()) return; // browsers fire emulated mouse events after a tap
    const link = ev.target.closest("a.term");
    if (link) showPop(link, false);
  });
  document.addEventListener("mouseout", (ev) => {
    if (isTouch()) return;
    if (ev.target.closest("a.term")) hidePop();
  });
  document.addEventListener("focusin", (ev) => {
    if (isTouch()) return; // a tap also focuses the link; the click handler decides instead
    const link = ev.target.closest("a.term");
    if (link) showPop(link, false); else hidePop();
  });
  document.addEventListener("click", (ev) => {
    const link = ev.target.closest("a.term");
    // first tap on a term: show the preview instead of following the link
    if (link && isTouch() && link !== popFor && showPop(link, true)) {
      ev.preventDefault();
      return;
    }
    hidePop();
  });
  // hide when the page scrolls, ignoring the small jitter a tap can cause
  window.addEventListener("scroll", () => {
    if (!pop.hidden && Math.abs(window.scrollY - popScrollY) > 24) hidePop();
  }, { passive: true });

  // ---------------------------------------------------------- active chapter in the table of contents
  const tocLinks = Array.from(document.querySelectorAll(".toc a"));
  const heads = tocLinks.map((a) => document.getElementById(a.getAttribute("href").slice(1))).filter(Boolean);
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          tocLinks.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${e.target.id}`));
        }
      }
    }, { rootMargin: "-80px 0px -70% 0px" });
    heads.forEach((h) => io.observe(h));
  }

  // ---------------------------------------------------------- back-to-top button
  const up = document.createElement("button");
  up.className = "to-top";
  up.type = "button";
  up.title = "Do góry";
  up.textContent = "↑";
  up.hidden = true;
  up.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  document.body.appendChild(up);
  window.addEventListener("scroll", () => { up.hidden = window.scrollY < 600; }, { passive: true });

  // ---------------------------------------------------------- copy entry link + toast
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  toast.hidden = true;
  document.body.appendChild(toast);
  let toastTimer = 0;

  function notify(message) {
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2200);
  }

  // Fallback for browsers without the async Clipboard API (e.g. some file:// setups).
  function legacyCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.className = "sr";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
    area.remove();
    return ok;
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); return true; } catch (_) { /* fall through */ }
    }
    return legacyCopy(text);
  }

  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button.copy-link");
    if (!btn) return;
    const url = `${location.href.split("#")[0]}#${btn.dataset.anchor}`;
    const ok = await copyText(url);
    notify(ok ? "Skopiowano link do schowka" : "Nie udało się skopiować linku");
  });

  applySelection();
  route();
})();
