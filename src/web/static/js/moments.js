// Spike: moment picker, shared by "Swap" / "Pick moments" on the clip page and "Combine moments" on the review page.
// Lists every stored candidate of a video. Tick moments, choose a concept, build. The count rule is checked live.
// The server builds the segments, the model fills in only the missing text, and the render is queued as a worker job.

(function () {
  const RULES = { single: [1, 1], story: [2, 3], pov: [1, 1], top3: [3, 3], top5: [5, 5] };
  const NAMES = { single: 'Single', story: 'Story', pov: 'POV', top3: 'Top 3', top5: 'Top 5' };
  const dlg = document.getElementById('moment-picker');
  if (!dlg) return;
  const list = dlg.querySelector('[data-mp-list]');
  const hint = dlg.querySelector('[data-mp-hint]');
  const build = dlg.querySelector('[data-mp-build]');
  const title = dlg.querySelector('[data-mp-title]');
  const picker = dlg.querySelector('[data-mp-concepts]');
  let state = null;   // { videoId, clipId, concept, swap, picked: [ids in the order they were ticked], moments }

  function rule(concept, n) {
    const [lo, hi] = RULES[concept];
    if (n >= lo && n <= hi) return '';
    if (lo === hi) return `${NAMES[concept]} needs exactly ${lo} moment${lo > 1 ? 's' : ''} (${n} picked)`;
    return `${NAMES[concept]} needs ${lo} to ${hi} moments (${n} picked)`;
  }

  function refresh() {
    const swap = state.swap;
    const n = swap ? state.picked.length : state.picked.length;
    const msg = swap ? (n === 1 ? '' : 'Pick the one moment to swap in') : rule(state.concept, n);
    hint.textContent = msg || (swap ? 'Ready to swap.' : `${NAMES[state.concept]} with ${n} moment${n > 1 ? 's' : ''}. The order you ticked them is kept.`);
    hint.classList.toggle('is-wrong', Boolean(msg));
    build.disabled = Boolean(msg) || state.busy;
    picker.querySelectorAll('input').forEach((r) => { r.checked = r.value === state.concept; });
    list.querySelectorAll('input[type="checkbox"]').forEach((box) => {
      const k = state.picked.indexOf(Number(box.value));
      box.checked = k >= 0;
      const order = box.closest('.mp-row').querySelector('.mp-order');
      order.textContent = k >= 0 && !swap ? String(k + 1) : '';
    });
  }

  function row(m) {
    const li = document.createElement('li');
    li.className = 'mp-row';
    const status = m.status === 'selected' ? 'Picked' : m.status === 'hubris' ? 'Setup line' : m.status === 'low_score' ? 'Not picked' : m.status === 'rejected' ? 'Rejected' : m.status;
    li.innerHTML = `
      <label class="mp-row__check"><input type="checkbox" value="${m.id}" aria-label="Pick: ${escapeHtml(m.title)}"><span class="mp-order" aria-hidden="true"></span></label>
      ${m.link ? `<a class="time-chip" href="${m.link}" target="_blank" rel="noopener" title="Open the source at ${m.time}">${m.time}</a>` : `<span class="time-chip">${m.time}</span>`}
      <span class="mp-row__title">${escapeHtml(m.title)}<span class="mp-row__meta">${escapeHtml(m.humor || '')}${m.humor ? ', ' : ''}${status}</span></span>
      <span class="badge badge--score ${m.score >= 60 ? '' : 'badge--muted'}">${m.score == null ? '-' : m.score}</span>`;
    li.querySelector('input').addEventListener('change', (e) => {
      const id = Number(e.target.value);
      if (state.swap) state.picked = e.target.checked ? [id] : [];   // a swap takes exactly one new moment
      else if (e.target.checked) state.picked.push(id);
      else state.picked = state.picked.filter((x) => x !== id);
      refresh();
    });
    return li;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  async function open(opts) {
    state = { videoId: opts.videoId, clipId: opts.clipId || null, concept: opts.concept || 'top3', swap: opts.swap || null,
              picked: (opts.preselect || []).filter(Boolean), moments: [], busy: false };
    title.textContent = state.swap ? 'Swap this entry' : 'Pick moments';
    picker.hidden = Boolean(state.swap);
    build.textContent = state.swap ? 'Swap in' : 'Build clip';
    list.innerHTML = '<li class="mp-empty">Loading moments…</li>';
    hint.textContent = '';
    build.disabled = true;
    dlg.showModal();
    try {
      const r = await fetch(`/videos/${state.videoId}/moments`);
      if (!r.ok) throw new Error();
      state.moments = (await r.json()).moments;
    } catch (_) {
      list.innerHTML = '<li class="mp-empty" role="alert">Could not load the moments. Close this and try again.</li>';
      return;
    }
    const keep = new Set(state.swap ? state.swap.ids : []);
    const shown = state.moments.filter((m) => !keep.has(m.id));
    list.innerHTML = '';
    if (!shown.length) list.innerHTML = '<li class="mp-empty">No stored moments for this video yet.</li>';
    shown.forEach((m) => list.appendChild(row(m)));
    if (state.swap) state.picked = [];
    refresh();
  }

  picker.addEventListener('change', (e) => {
    if (e.target.name !== 'mp-concept') return;
    state.concept = e.target.value;
    refresh();
  });

  build.addEventListener('click', async () => {
    let ids = state.picked.slice();
    if (state.swap) {
      ids = state.swap.ids.slice();
      ids[state.swap.index] = state.picked[0];     // the new moment takes the place of the swapped entry
    }
    state.busy = true;
    build.disabled = true;
    build.classList.add('is-loading');
    hint.textContent = 'Building. The editor is writing the missing text; this can take a minute…';
    try {
      const r = await fetch(`/videos/${state.videoId}/concept`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept: state.concept, candidate_ids: ids, clip_id: state.clipId }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || 'Could not build the clip.');
      dlg.close();
      if (typeof showToast === 'function') showToast('Queued. The clip renders in the background.');
      setTimeout(() => location.reload(), 600);
    } catch (err) {
      hint.textContent = err.message;
      hint.classList.add('is-wrong');
    } finally {
      state.busy = false;
      build.classList.remove('is-loading');
      if (dlg.open) refresh();
    }
  });

  dlg.querySelector('[data-mp-cancel]').addEventListener('click', () => dlg.close());
  window.openMomentPicker = open;
})();
