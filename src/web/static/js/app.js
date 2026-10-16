// Spike: Main Client-side Script (DESIGN.md §2, §9.10, §9.13, §9.15, §13)

document.addEventListener("DOMContentLoaded", () => {
  initVideoPreviews();
  initShortcuts();
  initToasts();
  initDialogs();
  initDropzones();
});

// ── Hover/Focus Video Previews for Clip Cards (DESIGN.md §9.10) ──────────────
function initVideoPreviews() {
  const cards = document.querySelectorAll(".clip-card");
  cards.forEach((card) => {
    const video = card.querySelector("video");
    if (!video) return;

    function playPreview() {
      if (video.dataset.src && !video.src) {
        video.src = video.dataset.src;
      }
      video.muted = true;
      video.play().catch(() => {});
    }

    function pausePreview() {
      video.pause();
    }

    card.addEventListener("mouseenter", playPreview);
    card.addEventListener("mouseleave", pausePreview);
    card.addEventListener("focusin", playPreview);
    card.addEventListener("focusout", pausePreview);
  });
}

// ── Keyboard Shortcuts (DESIGN.md §1, §10.1, §10.2, §13) ─────────────────────
function initShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Disable shortcuts while typing in form elements
    const tag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
    if (["input", "textarea", "select"].includes(tag) || document.activeElement.isContentEditable) {
      return;
    }

    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const key = e.key.toLowerCase();

    // Toggle shortcuts dialog
    if (e.key === "?") {
      const diag = document.getElementById("shortcuts-dialog");
      if (diag) {
        if (diag.open) diag.close();
        else diag.showModal();
        e.preventDefault();
      }
      return;
    }

    // Play/Pause video on Space
    if (e.code === "Space") {
      const activeVideo = document.querySelector(".player-container video") || document.querySelector("video");
      if (activeVideo) {
        e.preventDefault();
        if (activeVideo.paused) activeVideo.play();
        else activeVideo.pause();
      }
      return;
    }

    // Approve clip ('a')
    if (key === "a") {
      const approveBtn = document.getElementById("btn-approve");
      if (approveBtn && !approveBtn.disabled) {
        e.preventDefault();
        approveBtn.click();
      }
      return;
    }

    // Reject clip ('r')
    if (key === "r") {
      const rejectDiag = document.getElementById("reject-dialog");
      if (rejectDiag) {
        e.preventDefault();
        rejectDiag.showModal();
      }
      return;
    }

    // Download clip ('d')
    if (key === "d") {
      const downloadBtn = document.getElementById("btn-download");
      if (downloadBtn) {
        e.preventDefault();
        downloadBtn.click();
      }
      return;
    }

    // Edit captions ('e')
    if (key === "e") {
      const hookInput = document.getElementById("field-hook-text") || document.getElementById("field-captions");
      if (hookInput) {
        e.preventDefault();
        hookInput.focus();
      }
      return;
    }

    // Next / Previous clips ('j' / 'k')
    if (key === "j") {
      const nextLink = document.getElementById("nav-next-clip");
      if (nextLink) {
        e.preventDefault();
        window.location.href = nextLink.href;
      }
    } else if (key === "k") {
      const prevLink = document.getElementById("nav-prev-clip");
      if (prevLink) {
        e.preventDefault();
        window.location.href = prevLink.href;
      }
    }
  });
}

// ── Toasts (DESIGN.md §9.13) ─────────────────────────────────────────────────
function initToasts() {
  document.body.addEventListener("htmx:afterOnLoad", (evt) => {
    const triggerHeader = evt.detail.xhr.getResponseHeader("HX-Trigger");
    if (triggerHeader) {
      try {
        const data = JSON.parse(triggerHeader);
        if (data.toast && data.toast.message) {
          showToast(data.toast.message);
        }
      } catch (e) {}
    }
  });

  window.showToast = showToast;
  initRenderNotifications();
}

// Rerender outcomes are polled on every page, so a render started elsewhere still reports back.
function initRenderNotifications() {
  const KEY = "spikeRenderSeen";
  // Toasts are kept in sessionStorage until they expire, because the Review and clip pages
  // auto-reload when a render finishes and a reload would otherwise wipe the toast.
  const TTL = 8000, QKEY = "spikeToastQueue", shown = new Set();
  const load = () => { try { return JSON.parse(sessionStorage.getItem(QKEY) || "[]"); } catch (e) { return []; } };
  const queue = (t) => sessionStorage.setItem(QKEY, JSON.stringify(load().concat(t)));
  const flush = () => {
    const live = load().filter((t) => t.exp > Date.now());
    sessionStorage.setItem(QKEY, JSON.stringify(live));
    live.forEach((t) => {
      if (shown.has(t.id)) return;
      shown.add(t.id);
      showToast(t.msg, t.kind, t.href, t.exp - Date.now());
    });
  };
  const get = async (after) => {
    const res = await fetch("/api/render-events" + (after === null ? "" : "?after=" + after));
    return res.ok ? res.json() : null;
  };
  const poll = async () => {
    if (document.hidden) return;
    try {
      // Stored as "epoch:lastId". A new epoch means the server restarted and event ids began again.
      const [epoch, last] = (sessionStorage.getItem(KEY) || ":").split(":");
      let data = await get(last === "" ? null : last);
      if (data && epoch && epoch !== String(data.epoch)) data = await get(0);
      if (!data) return;
      data.events.forEach((e) => {
        queue({
          id: e.id + "@" + data.epoch,
          msg: (e.ok ? "Clip rendered: " : "Render failed: ") + e.title,
          kind: e.ok ? "success" : "danger",
          href: "/clips/" + e.clip_id,
          exp: Date.now() + TTL,
        });
      });
      flush();
      sessionStorage.setItem(KEY, data.epoch + ":" + data.last);
    } catch (e) {}
  };
  flush();
  poll();
  setInterval(poll, 3000);
}

function showToast(message, kind, href, ms) {
  let region = document.querySelector(".toast-region");
  if (!region) {
    region = document.createElement("div");
    region.className = "toast-region";
    region.setAttribute("aria-live", "polite");
    document.body.appendChild(region);
  }

  const toast = document.createElement("div");
  toast.className = "toast" + (kind ? " toast--" + kind : "");

  const span = document.createElement("span");
  if (href) {
    const a = document.createElement("a");
    a.href = href;
    a.textContent = message;
    span.appendChild(a);
  } else {
    span.textContent = message; // Safe textContent, never innerHTML
  }

  const closeBtn = document.createElement("button");
  closeBtn.className = "btn btn--ghost btn--sm btn--icon";
  closeBtn.setAttribute("aria-label", "Close notification");
  closeBtn.innerHTML = '<svg width="14" height="14" aria-hidden="true"><use href="/static/icons/sprite.svg#x"></use></svg>';
  closeBtn.addEventListener("click", () => toast.remove());

  toast.appendChild(span);
  toast.appendChild(closeBtn);
  region.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, ms || 5000);
}

// ── Native Dialogs (DESIGN.md §9.15) ─────────────────────────────────────────
function initDialogs() {
  const dialogs = document.querySelectorAll("dialog");
  dialogs.forEach((dialog) => {
    dialog.addEventListener("click", (e) => {
      // Backdrop click closes modal
      if (e.target === dialog) {
        dialog.close();
      }
    });

    const closeBtns = dialog.querySelectorAll("[data-close-dialog]");
    closeBtns.forEach((btn) => {
      btn.addEventListener("click", () => dialog.close());
    });
  });
}

// ── Dropzone Handlers (DESIGN.md §10.4) ───────────────────────────────────────
function initDropzones() {
  const dropzones = document.querySelectorAll(".dropzone");
  dropzones.forEach((zone) => {
    const fileInput = zone.querySelector('input[type="file"]');
    if (!fileInput) return;

    zone.addEventListener("click", () => fileInput.click());

    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("is-dragover");
    });

    zone.addEventListener("dragleave", () => {
      zone.classList.remove("is-dragover");
    });

    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("is-dragover");
      if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        updateDropzoneLabel(zone, e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", () => {
      if (fileInput.files.length > 0) {
        updateDropzoneLabel(zone, fileInput.files[0]);
      }
    });
  });
}

function updateDropzoneLabel(zone, file) {
  const title = zone.querySelector(".dropzone__title");
  const help = zone.querySelector(".dropzone__help");
  if (title) title.textContent = file.name;
  if (help) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    help.textContent = `${mb} MB selected`;
  }
}

// ── Theme Toggle ─────────────────────────────────────────────────────────────
window.toggleTheme = function() {
  const root = document.documentElement;
  const current = root.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  document.cookie = `spike_theme=${next};path=/;max-age=31536000;SameSite=Lax`;
};

// ── Source form: ID help toggle + channel lookup autocomplete ────────────────
document.addEventListener("DOMContentLoaded", () => {
  const infoBtn = document.getElementById("ext-id-info-btn");
  const infoPanel = document.getElementById("ext-id-info");
  if (infoBtn && infoPanel) {
    infoBtn.addEventListener("click", () => {
      infoPanel.hidden = !infoPanel.hidden;
      infoBtn.setAttribute("aria-expanded", String(!infoPanel.hidden));
    });
  }

  const input = document.getElementById("field-ext-id");
  const list = document.getElementById("ext-id-results");
  if (!input || !list || !input.dataset.lookup) return;
  const kind = document.getElementById("field-kind");
  const nameInput = document.getElementById("field-name");
  const status = document.getElementById("ext-id-status");
  const idleText = status.textContent;
  let timer = null;
  let seq = 0;
  let lastAutofill = nameInput.value;

  const hide = () => { list.hidden = true; list.replaceChildren(); };
  const countLabel = (n) =>
    new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n) +
    (kind.value === "youtube" ? " subscribers" : " followers");

  function pick(r) {
    input.value = r.id;
    // Don't overwrite a display name the user typed themselves.
    if (!nameInput.value || nameInput.value === lastAutofill) {
      nameInput.value = r.name;
      lastAutofill = r.name;
    }
    status.textContent = `Matched: ${r.name}${r.sub ? " (" + r.sub + ")" : ""}${r.followers != null ? ", " + countLabel(r.followers) : ""}`;
    hide();
  }

  function render(results) {
    list.replaceChildren();
    results.forEach((r) => {
      const li = document.createElement("li");
      li.className = "lookup__item";
      li.setAttribute("role", "option");
      if (r.thumb) {
        const img = document.createElement("img");
        img.className = "lookup__thumb";
        img.src = r.thumb;
        img.alt = "";
        li.appendChild(img);
      }
      const text = document.createElement("div");
      text.className = "lookup__text";
      const name = document.createElement("span");
      name.className = "lookup__name";
      name.textContent = r.name;
      const sub = document.createElement("span");
      sub.className = "lookup__sub";
      sub.textContent = [r.sub, r.id].filter(Boolean).join(" · ");
      text.append(name, sub);
      li.appendChild(text);
      if (r.followers != null) {
        const count = document.createElement("span");
        count.className = "lookup__count";
        count.textContent = countLabel(r.followers);
        li.appendChild(count);
      }
      li.addEventListener("mousedown", (e) => { e.preventDefault(); pick(r); });
      list.appendChild(li);
    });
    list.hidden = results.length === 0;
  }

  async function search() {
    const q = input.value.trim();
    if (q.length < 2) { hide(); status.textContent = idleText; return; }
    const mine = ++seq;
    status.textContent = "Searching...";
    // A pasted YouTube channel ID can only be YouTube, whatever the dropdown says.
    if (/^UC[\w-]{22}$/.test(q)) kind.value = "youtube";
    try {
      const res = await fetch(`${input.dataset.lookup}?kind=${encodeURIComponent(kind.value)}&q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (mine !== seq) return; // a newer keystroke superseded this request
      if (data.error) { hide(); status.textContent = data.error; return; }
      if (!data.results.length) { hide(); status.textContent = "No channel found. You can still save the value as typed."; return; }
      // Exact ID/login typed or pasted: confirm it directly instead of listing.
      const exact = data.results.find((r) => r.id.toLowerCase() === q.toLowerCase());
      if (exact) { pick(exact); return; }
      status.textContent = "Pick a result to fill the ID and display name.";
      render(data.results);
    } catch (e) {
      if (mine === seq) { hide(); status.textContent = "Lookup failed. Enter the ID manually."; }
    }
  }

  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 400); });
  kind.addEventListener("change", () => { if (input.value.trim()) search(); });
  input.addEventListener("blur", hide);
  input.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
});

// ── New job (From streamer): "add source" shortcut + recent-VOD picker ───────
document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("field-source");
  const input = document.getElementById("field-vod-url");
  const list = document.getElementById("vod-results");
  const status = document.getElementById("vod-status");
  if (!select || !input || !list) return;

  const idleText = status.textContent;
  let vods = [];
  let seq = 0;

  const hide = () => { list.hidden = true; };

  function render() {
    const q = input.value.trim().toLowerCase();
    const shown = vods.filter((v) => !q || v.title.toLowerCase().includes(q) || v.id.toLowerCase().includes(q));
    list.replaceChildren();
    shown.forEach((v) => {
      const li = document.createElement("li");
      li.className = "lookup__item";
      li.setAttribute("role", "option");
      const text = document.createElement("div");
      text.className = "lookup__text";
      const title = document.createElement("span");
      title.className = "lookup__name";
      title.textContent = v.title || v.id;
      const sub = document.createElement("span");
      sub.className = "lookup__sub";
      sub.textContent = v.url;
      text.append(title, sub);
      li.appendChild(text);
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        input.value = v.url;
        status.textContent = `Selected: ${v.title || v.id}`;
        hide();
      });
      list.appendChild(li);
    });
    list.hidden = shown.length === 0;
  }

  async function loadVods() {
    vods = [];
    hide();
    const id = select.value;
    if (!id) { status.textContent = idleText; return; }
    const mine = ++seq;
    status.textContent = "Loading recent videos...";
    try {
      const res = await fetch(`/new/vods?source_id=${encodeURIComponent(id)}`);
      const data = await res.json();
      if (mine !== seq) return; // source changed while loading
      vods = data.results || [];
      status.textContent = vods.length
        ? "Choose a recent video, or paste a link. Leave empty for the latest."
        : "No recent videos found. You can still paste a link.";
    } catch (e) {
      if (mine === seq) status.textContent = "Couldn't load recent videos. You can still paste a link.";
    }
  }

  select.addEventListener("change", () => {
    if (select.value === "__new__") {
      select.value = ""; // so Back doesn't leave the placeholder value selected
      window.location.href = "/sources/new";
      return;
    }
    loadVods();
  });
  input.addEventListener("focus", render);
  input.addEventListener("input", render);
  input.addEventListener("blur", hide);
  input.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  if (select.value) loadVods();
});

// ── Bulk selection forms (Outreach) ──────────────────────────────────────────
// [data-select-all] toggles every name="ids" checkbox in its form; [data-selected-count] shows the total.
// Any submit button with data-confirm asks first.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-bulk-form]").forEach((form) => {
    const boxes = () => Array.from(form.querySelectorAll('input[name="ids"]'));
    const alls = form.querySelectorAll("[data-select-all]");
    const counter = form.querySelector("[data-selected-count]");
    const refresh = () => {
      const all = boxes();
      const n = all.filter((b) => b.checked).length;
      if (counter) counter.textContent = n ? `${n} selected` : "None selected";
      alls.forEach((a) => {
        a.checked = n > 0 && n === all.length;
        a.indeterminate = n > 0 && n < all.length;
      });
    };
    form.addEventListener("change", (e) => {
      if (e.target.matches("[data-select-all]")) boxes().forEach((b) => { b.checked = e.target.checked; });
      if (e.target.matches("[data-select-all], input[name='ids']")) refresh();
    });
    refresh();
  });
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-confirm]");
  if (btn && !window.confirm(btn.dataset.confirm)) e.preventDefault();
});

// Forms with data-warn-unsaved ask before leaving with typed edits (email drafts, templates)
document.addEventListener("DOMContentLoaded", () => {
  const forms = document.querySelectorAll("form[data-warn-unsaved]");
  if (!forms.length) return;
  let dirty = false;
  forms.forEach((f) => {
    f.addEventListener("input", (e) => { if (e.target.matches("input:not([type=checkbox]), textarea")) dirty = true; });
    f.addEventListener("submit", () => { dirty = false; });
  });
  window.addEventListener("beforeunload", (e) => { if (dirty) e.preventDefault(); });
});

// [data-open-dialog="id"] opens that <dialog>; a dialog with data-open-on-load opens itself (form errors)
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-open-dialog]");
  const dialog = btn && document.getElementById(btn.dataset.openDialog);
  if (dialog) dialog.showModal();
});
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("dialog[data-open-on-load]").forEach((d) => d.showModal());
});

// select[data-sets-fields]: each option's data-defaults ({"field-id": "value"}) fills those fields, except
// fields the person already changed (Outreach saved searches: live vs re-upload sizes)
document.addEventListener("change", (e) => {
  const sel = e.target.closest("select[data-sets-fields]");
  if (!sel) return;
  const all = Array.from(sel.options).map((o) => JSON.parse(o.dataset.defaults || "{}"));
  const chosen = JSON.parse(sel.selectedOptions[0].dataset.defaults || "{}");
  Object.entries(chosen).forEach(([id, value]) => {
    const input = document.getElementById(id);
    if (input && (!input.value || all.some((d) => d[id] === input.value))) input.value = value;
  });
});

// ── Setup requirements popup ─────────────────────────────────────────────────
// A form (or submit button) with data-requires="<action>" is checked against /requirements/check first.
// data-requires-fields="a,b" sends those form fields; data-requires-kind sends a fixed platform.
// Anything missing opens a popup listing the steps and blocks the submit; otherwise the submit goes through.
function showRequirements(items) {
  document.getElementById("requirements-dialog")?.remove();
  const dlg = document.createElement("dialog");
  dlg.id = "requirements-dialog";
  dlg.className = "dialog";
  const body = document.createElement("div");
  body.className = "dialog__body";
  const h = document.createElement("h2");
  h.className = "dialog__title";
  h.textContent = "Finish setup first";
  const p = document.createElement("p");
  p.className = "dialog__text";
  p.textContent = "This needs the following before it can run:";
  const list = document.createElement("div");
  list.className = "stack stack--sm";
  list.style.marginTop = "var(--space-4)";
  items.forEach((it) => {
    const row = document.createElement("div");
    const t = document.createElement("strong");
    t.textContent = it.title;
    const d = document.createElement("p");
    d.className = "dialog__text";
    d.textContent = it.detail;
    row.append(t, d);
    if (it.fix_url) {
      const a = document.createElement("a");
      a.className = "btn btn--primary btn--sm";
      a.href = it.fix_url;
      a.textContent = it.fix_label || "Fix";
      a.style.marginTop = "var(--space-2)";
      row.appendChild(a);
    }
    list.appendChild(row);
  });
  body.append(h, p, list);
  const foot = document.createElement("div");
  foot.className = "dialog__footer";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "btn btn--secondary";
  close.textContent = "Close";
  close.addEventListener("click", () => dlg.close());
  foot.appendChild(close);
  dlg.append(body, foot);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

document.addEventListener("submit", async (e) => {
  const form = e.target;
  const sub = e.submitter;
  const holder = (sub && sub.dataset.requires) ? sub : (form.dataset.requires ? form : null);
  if (!holder || form._requirementsOk) return;
  e.preventDefault();
  e.stopPropagation(); // the page's own submit handler runs only once the check passes
  const q = new URLSearchParams({ action: holder.dataset.requires });
  if (holder.dataset.requiresKind) q.set("kind", holder.dataset.requiresKind);
  (holder.dataset.requiresFields || "").split(",").filter(Boolean).forEach((name) => {
    const field = form.elements[name];
    if (!field) return;
    const key = name === "url" ? "url" : name;
    if (field.value) q.set(key, field.value);
  });
  let missing = [];
  try {
    const res = await fetch("/requirements/check?" + q);
    if (res.ok) missing = (await res.json()).missing || [];
  } catch (_) { /* server unreachable: let the submit hit the server's own check */ }
  if (missing.length) { showRequirements(missing); return; }
  form._requirementsOk = true;
  form.requestSubmit(sub || undefined);
  form._requirementsOk = false;
}, true);
