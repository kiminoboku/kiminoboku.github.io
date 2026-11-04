// Tab navigation, glossary search and definition tooltips.
// No external dependencies, no eval and no HTML built from data (works under a strict CSP).
// The UI strings are Polish because the page is Polish.
(function () {
  "use strict";

  const panels = {
    rules: document.getElementById("rules"),
    glossary: document.getElementById("glossary"),
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
  const totalEntries = panels.glossary.querySelectorAll(".entry").length;

  function filter() {
    const q = norm(input.value.trim());
    let shown = 0;
    for (const it of items) {
      const hit = !q || it.name.includes(q) || (fullText.checked && it.text.includes(q));
      it.el.hidden = !hit;
      if (hit && it.el.classList.contains("entry")) shown++;
    }
    for (const g of groups) {
      const visible = g.querySelector(".entry:not([hidden]), .alias:not([hidden])");
      const headHit = q && norm(g.querySelector(".group-title").textContent).includes(q);
      if (headHit) g.querySelectorAll(".entry, .alias").forEach((el) => { if (!visible) el.hidden = false; });
      g.hidden = !visible && !headHit;
    }
    for (const L of letters) {
      L.hidden = !L.querySelector(".entry:not([hidden]), .alias:not([hidden])");
      const link = panels.glossary.querySelector(`.letters a[href="#${L.id}"]`);
      if (link) link.classList.toggle("off", L.hidden);
    }
    empty.hidden = letters.some((L) => !L.hidden);
    counter.textContent = q ? `Znaleziono haseł: ${shown}` : `Haseł: ${totalEntries}`;
  }
  input.addEventListener("input", () => { filter(); window.scrollTo(0, 0); });
  fullText.addEventListener("change", filter);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { input.value = ""; filter(); }
  });

  // ---------------------------------------------------------- hash routing
  function route() {
    const id = decodeURIComponent(location.hash.slice(1));
    const el = id ? document.getElementById(id) : null;
    if (id === "glossary" || (el && panels.glossary.contains(el))) {
      show("glossary");
      if (el && el.closest("[hidden]") && input.value) { input.value = ""; filter(); }
    } else {
      show("rules");
    }
    if (el && el !== panels.glossary && el !== panels.rules) {
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
    const target = document.getElementById(link.getAttribute("href").slice(1));
    if (!target || !target.classList.contains("entry")) return false;
    const title = document.createElement("strong");
    title.textContent = target.querySelector("h3 .t").textContent;
    const body = document.createElement("div");
    const def = target.querySelector(".def p");
    body.textContent = def ? def.textContent : "";
    const parts = [title, body];
    if (withOpenLink) {
      const open = document.createElement("a");
      open.className = "pop-open";
      open.href = link.getAttribute("href");
      open.textContent = "Otwórz hasło →";
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

  filter();
  route();
})();
