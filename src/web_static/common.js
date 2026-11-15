/* romm_tools shared page script (served at /common.js; the ROM folders page loads ../common.js).
   The grouped menu in the top bar, the phone menu button, and - on pages that ask for it - the connection
   pill and the Sync now button. Each page still marks its current item with class "on" on `.nav a`. */
(function () {
  "use strict";
  const RT = window.RT = window.RT || {};

  function setupMenu() {
    const nav = document.querySelector("header.top .nav");
    if (!nav || nav.dataset.rtMenu) return;
    nav.dataset.rtMenu = "1";
    const menuBtn = document.querySelector("header.top .menu-btn");
    const groups = [...nav.querySelectorAll(".grp")];

    const closeAll = except => groups.forEach(g => {
      if (g !== except) { g.classList.remove("open"); g.querySelector(".grp-btn").setAttribute("aria-expanded", "false"); }
    });
    const closePhone = () => {
      if (!menuBtn) return;
      nav.classList.remove("open");
      menuBtn.setAttribute("aria-expanded", "false");
    };

    // Group buttons show the page you're on ("Platforms ▾") and a dot when a page inside needs you.
    // Only writes what changed: the observer below sees our own writes too.
    const refresh = () => {
      groups.forEach(g => {
        const cur = g.querySelector(".grp-menu a.on");
        if (g.classList.contains("on") !== !!cur) g.classList.toggle("on", !!cur);
        const label = g.querySelector(".grp-btn .gl");
        const text = cur ? (cur.dataset.short || cur.firstChild.textContent.trim()) : g.dataset.label;
        if (label && label.textContent !== text) label.textContent = text;
        const alert = [...g.querySelectorAll(".grp-menu .n.alert")].some(n => !n.hidden && n.textContent.trim());
        if (g.classList.contains("alert") !== alert) g.classList.toggle("alert", alert);
        const hide = ![...g.querySelectorAll(".grp-menu a")].some(a => !a.hidden);
        if (!g.hasAttribute("data-feature") && g.hidden !== hide) g.hidden = hide;
      });
    };
    new MutationObserver(refresh).observe(nav, {subtree: true, attributes: true, attributeFilter: ["class", "hidden"],
                                                childList: true, characterData: true});
    refresh();

    groups.forEach(g => {
      const b = g.querySelector(".grp-btn");
      b.addEventListener("click", e => {
        e.stopPropagation();
        const open = !g.classList.contains("open");
        closeAll(g);
        g.classList.toggle("open", open);
        b.setAttribute("aria-expanded", String(open));
        if (open) { const first = g.querySelector(".grp-menu a:not([hidden])"); if (first && e.detail === 0) first.focus(); }
      });
    });
    nav.addEventListener("click", e => { if (e.target.closest("a")) { closeAll(); closePhone(); } });
    document.addEventListener("click", e => { if (!e.target.closest("header.top .nav") && !e.target.closest(".menu-btn")) { closeAll(); closePhone(); } });
    document.addEventListener("keydown", e => { if (e.key === "Escape") { closeAll(); closePhone(); } });
    if (menuBtn) menuBtn.addEventListener("click", e => {
      e.stopPropagation();
      const open = !nav.classList.contains("open");
      nav.classList.toggle("open", open);
      menuBtn.setAttribute("aria-expanded", String(open));
    });
    window.addEventListener("hashchange", () => { closeAll(); closePhone(); });
  }

  // Connection pill + Sync now for a page that doesn't run save sync itself (the ROM folders page).
  RT.syncControls = function ({base = "", pill, button}) {
    const p = document.querySelector(pill), b = document.querySelector(button);
    if (!p || !b) return;
    p.hidden = false; b.hidden = false;
    let timer = null;
    const show = (dot, text) => { p.innerHTML = `<span class="dot ${dot}"></span><span>${text}</span>`; };
    const tick = async () => {
      clearTimeout(timer);
      let busy = false;
      try {
        const r = await fetch(base + "api/health", {cache: "no-store"});
        const d = await r.json();
        busy = ["building", "fetching", "syncing", "applying", "starting"].includes(d.phase);
        if (d.problem) show("bad", "problem");
        else show(busy ? "busy" : "ok", busy ? "working" : "connected");
        p.title = d.problem || "";
      } catch (e) { show("bad", "offline"); }
      b.disabled = busy;
      b.innerHTML = busy ? `⟳<span class="lbl"> Syncing…</span>` : `⟳<span class="lbl"> Sync now</span>`;
      timer = setTimeout(tick, document.hidden ? 60000 : busy ? 2000 : 15000);
    };
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await fetch(base + "api/sync", {method: "POST"}); } catch (e) { /* the pill shows it */ }
      setTimeout(tick, 800);
    });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
    tick();
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupMenu);
  else setupMenu();
})();
