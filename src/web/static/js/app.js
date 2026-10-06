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
