// New job page: Stream or Anime. Anime shows its own details and hides the stream render presets
// (anime has its own defaults). Hidden fieldsets are disabled, so their fields are not sent.
(() => {
  const kinds = document.querySelectorAll('input[name="kind"]');
  if (!kinds.length) return;
  const anime = document.getElementById('anime-fields');
  const render = document.getElementById('render-presets');
  const help = document.getElementById('kind-help');
  const sync = () => {
    const on = document.querySelector('input[name="kind"]:checked').value === 'anime';
    anime.hidden = anime.disabled = !on;
    render.hidden = render.disabled = on;
    help.textContent = on ? help.dataset.anime : help.dataset.stream;
  };
  kinds.forEach((r) => r.addEventListener('change', sync));
  sync();  // also covers a choice the browser kept on Back
})();

// From anime tab: pick a trending or popular show, or search a title, then pick the season and episode and upload the file. Each season is its own AniList entry with its own
// id and episode count. Results are built with textContent only (titles come from outside).
(() => {
  const search = document.getElementById('field-anime-search');
  if (!search) return;
  const list = document.getElementById('anime-results');
  const status = document.getElementById('anime-status');
  const season = document.getElementById('field-anime-id');
  const episode = document.getElementById('field-anime-episode');
  const epHelp = document.getElementById('anime-ep-help');
  const label = document.getElementById('anime-label');
  const idle = status.textContent;
  let seasons = [];
  let seq = 0;
  let timer = null;

  const hide = () => { list.hidden = true; search.setAttribute('aria-expanded', 'false'); };
  const getJson = async (url) => {
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed.');
    return data;
  };
  const shelf = document.getElementById('anime-shelf');
  const file = document.getElementById('field-file');
  const fileHelp = document.getElementById('anime-file-help');
  const fileIdle = fileHelp.textContent;
  let fileGuess = null;  // {title, episode} read from the chosen file's name
  const detail = (s) => [s.format ? s.format.replace('_', ' ') : null, s.year, s.episodes ? `${s.episodes} episodes` : null]
    .filter(Boolean).join(' · ');
  // An airing show has no final count yet: cap at the last episode out.
  const lastEp = (s) => s.episodes || s.aired || null;
  const norm = (t) => (t || '').toLowerCase().replace(/[^a-z0-9]+/g, '');

  // Same patterns as parse_filename() in src/pipeline/stage1_anime.py: "[Group] Show - 12 [1080p]", "Show.S01E12", "Show Ep 12"
  function parseName(name) {
    let s = name.replace(/\.[^.]+$/, '').replace(/\[[^\]]*\]|\([^)]*\)/g, ' ').replace(/_/g, ' ').replace(/(?<=\w)\.(?=\w)/g, ' ');
    let ep = null;
    let cut = s.length;
    for (const rx of [/[Ss]\d{1,2}[Ee](\d{1,4})/, /\s-\s(\d{1,4})(?:v\d)?(?:\s|$|\[|\()/, /[Ee]p?(?:isode)?[ ._]?(\d{1,4})\b/]) {
      const m = rx.exec(s + ' ');
      if (m) { ep = Number(m[1]); cut = m.index; break; }
    }
    return { title: s.slice(0, cut).replace(/\s+/g, ' ').replace(/^[\s-]+|[\s-]+$/g, '') || null, episode: ep };
  }

  function syncSeason() {
    const s = seasons.find((x) => String(x.id) === season.value);
    if (!s) return;
    const max = lastEp(s);
    if (max) episode.max = max; else episode.removeAttribute('max');
    if (!episode.value) episode.value = 1;
    if (max && Number(episode.value) > max) episode.value = max;
    epHelp.textContent = s.episodes ? `${s.episodes} episodes in this season.`
      : s.aired ? `Airing now: episodes 1 to ${s.aired} are out.` : 'The episode count is not published yet.';
    label.value = `${s.title} episode ${episode.value}`;
    checkFile();
    markEps();
  }

  // The file name is a hint: it fills an empty episode and flags a show that does not match, but never blocks.
  function checkFile() {
    if (!fileGuess) { fileHelp.textContent = fileIdle; fileHelp.classList.remove('is-wrong'); return; }
    const s = seasons.find((x) => String(x.id) === season.value);
    const a = norm(fileGuess.title);
    const b = s ? norm(s.title) + norm(search.value) : '';
    const off = s && a.length > 3 && !b.includes(a) && !a.includes(norm(s.title));
    fileHelp.textContent = off ? `The file name says "${fileGuess.title}". Check that the show above is right.`
      : fileGuess.episode ? `Episode ${fileGuess.episode}, from the file name.` : 'No episode number in the file name. Set it above.';
    fileHelp.classList.toggle('is-wrong', Boolean(off));
  }

  file.addEventListener('change', () => {
    fileGuess = file.files.length ? parseName(file.files[0].name) : null;
    if (fileGuess && fileGuess.episode) {
      episode.value = fileGuess.episode;
      if (seasons.length) syncSeason();
    }
    if (fileGuess && fileGuess.title && !seasons.length && !search.value.trim()) {
      search.value = fileGuess.title;  // nothing picked yet: look the file's show up
      run();
    }
    checkFile();
  });

  function shelfCard(r) {
    const li = document.createElement('li');
    li.className = 'shelf__item';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'shelf__card';
    btn.setAttribute('aria-pressed', 'false');
    btn.dataset.id = r.id;
    const img = document.createElement('img');
    img.className = 'shelf__cover';
    img.alt = '';
    img.loading = 'lazy';
    img.width = 104;
    img.height = 156;
    if (r.cover) img.src = r.cover;
    const name = document.createElement('span');
    name.className = 'shelf__name';
    name.textContent = r.title;
    const sub = document.createElement('span');
    sub.className = 'shelf__sub';
    sub.textContent = r.aired ? `Ep ${r.aired} out` : r.episodes ? `${r.episodes} eps` : (r.year || '');
    btn.append(img, name, sub);
    btn.addEventListener('click', () => pick(r));
    li.appendChild(btn);
    return li;
  }

  async function loadShelf(kind) {
    shelf.setAttribute('aria-busy', 'true');
    shelf.replaceChildren(...Array.from({ length: 6 }, () => {
      const li = document.createElement('li');
      li.className = 'shelf__item shelf__item--skeleton';
      return li;
    }));
    try {
      const data = await getJson(`/new/anime/shelf?kind=${encodeURIComponent(kind)}`);
      if (document.querySelector('input[name="shelf_kind"]:checked').value !== kind) return;  // switched meanwhile
      shelf.replaceChildren(...(data.results || []).map(shelfCard));
      markShelf();
    } catch (e) {
      const li = document.createElement('li');
      li.className = 'shelf__empty';
      li.textContent = `${e.message} Search by title below instead.`;
      shelf.replaceChildren(li);
    }
    shelf.setAttribute('aria-busy', 'false');
  }

  // The card of the show being picked looks selected (any season of it counts).
  function markShelf() {
    const ids = new Set(seasons.map((s) => String(s.id)));
    shelf.querySelectorAll('.shelf__card').forEach((b) => b.setAttribute('aria-pressed', String(ids.has(b.dataset.id))));
  }

  document.querySelectorAll('input[name="shelf_kind"]').forEach((r) => r.addEventListener('change', () => loadShelf(r.value)));
  loadShelf('trending');

  // Which episode to pick: the season's MyAnimeList fan ratings (out of 5), forum replies, and filler/recap flags.
  const epBox = document.getElementById('anime-eps');
  const best = document.getElementById('anime-best');
  const epStatus = document.getElementById('anime-eps-status');
  const more = document.getElementById('anime-eps-more');
  const epList = document.getElementById('anime-ep-list');
  const epNote = document.getElementById('anime-eps-note');
  const LONG = 60;   // a longer season lists only its top 30: nobody scrolls 1,000 rows, the number box covers the rest
  let eps = [];
  let epSeq = 0;

  const sortBy = () => document.querySelector('input[name="ep_sort"]:checked').value;
  const byKey = (k) => (a, b) => (k === 'n' ? a.n - b.n : (b[k] || 0) - (a[k] || 0) || a.n - b.n);
  const choose = (n) => { episode.value = n; syncSeason(); };

  function epTags(e) {
    return [e.new && ['New', 'badge badge--accent'], e.filler && ['Filler', 'badge badge--muted'], e.recap && ['Recap', 'badge badge--muted']]
      .filter(Boolean).map(([t, c]) => { const b = document.createElement('span'); b.className = c; b.textContent = t; return b; });
  }

  function renderBest() {
    const top = eps.filter((e) => e.score && !e.recap).sort(byKey('score')).slice(0, 3);
    const fresh = eps.filter((e) => e.new && !top.includes(e)).slice(-2);
    best.replaceChildren(...[...top, ...fresh].map((e) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.dataset.n = e.n;
      b.textContent = e.score && top.includes(e) ? `Ep ${e.n} · ${e.score.toFixed(2)}` : `Ep ${e.n} · New`;
      if (e.title) b.title = e.title;
      b.addEventListener('click', () => choose(e.n));
      return b;
    }));
    epStatus.textContent = best.children.length ? '' : 'No fan ratings for this season yet.';
  }

  function renderList() {
    const k = sortBy();
    const long = eps.length > LONG;
    const rows = [...eps].sort(byKey(long && k === 'n' ? 'score' : k)).slice(0, long ? 30 : undefined);
    epList.replaceChildren(...rows.map((e) => {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'ep-row' + (e.filler || e.recap ? ' is-dim' : '');
      b.dataset.n = e.n;
      const n = document.createElement('span');
      n.className = 'ep-row__n';
      n.textContent = e.n;
      const title = document.createElement('span');
      title.className = 'ep-row__title';
      const t = document.createElement('span');
      t.textContent = e.title || `Episode ${e.n}`;
      title.append(t, ...epTags(e));
      const stats = document.createElement('span');
      stats.className = 'ep-row__stats';
      stats.textContent = [e.replies != null ? `${e.replies} replies` : null, e.score ? e.score.toFixed(2) : 'No rating'].filter(Boolean).join('  ');
      b.append(n, title, stats);
      b.addEventListener('click', () => choose(e.n));
      li.appendChild(b);
      return li;
    }));
    epNote.textContent = long ? `Showing the top 30 of ${eps.length} episodes. Type any episode number above.` : '';
    markEps();
  }

  // The chosen episode looks selected in the chips and the list.
  function markEps() {
    const v = String(episode.value);
    best.querySelectorAll('.chip').forEach((c) => c.classList.toggle('is-on', c.dataset.n === v));
    epList.querySelectorAll('.ep-row').forEach((r) => r.setAttribute('aria-pressed', String(r.dataset.n === v)));
  }

  async function loadEpisodes() {
    const s = seasons.find((x) => String(x.id) === season.value);
    const mine = ++epSeq;
    eps = [];
    best.replaceChildren();
    epList.replaceChildren();
    more.hidden = true;
    epBox.hidden = !(s && s.mal);
    if (epBox.hidden) return;
    epStatus.textContent = lastEp(s) > 200 ? 'Loading episode ratings. A long show takes up to half a minute the first time.' : 'Loading episode ratings...';
    try {
      const data = await getJson(`/new/anime/episodes?mal=${encodeURIComponent(s.mal)}`);
      if (mine !== epSeq) return;  // another season was picked meanwhile
      eps = data.episodes || [];
      document.getElementById('ep-sort-replies').disabled = !eps.some((e) => e.replies != null);
      renderBest();
      if (eps.length) { more.hidden = false; renderList(); }
    } catch (e) {
      if (mine === epSeq) epStatus.textContent = `${e.message} You can still type the episode number.`;
    }
  }

  document.querySelectorAll('input[name="ep_sort"]').forEach((r) => r.addEventListener('change', renderList));
  season.addEventListener('change', loadEpisodes);

  async function pick(r) {
    search.value = r.title;
    hide();
    const mine = ++seq;
    status.textContent = 'Loading seasons...';
    try {
      const data = await getJson(`/new/anime/seasons?id=${encodeURIComponent(r.id)}`);
      if (mine !== seq) return;  // another title was picked meanwhile
      seasons = data.seasons || [];
      season.replaceChildren();
      seasons.forEach((s, i) => {
        const o = document.createElement('option');
        o.value = s.id;
        o.textContent = `${i + 1}. ${s.title}${s.year ? ` (${s.year})` : ''}`;
        season.appendChild(o);
      });
      season.value = seasons.some((s) => s.id === r.id) ? r.id : (seasons[0] || {}).id;
      season.disabled = episode.disabled = !seasons.length;
      status.textContent = seasons.length > 1 ? `${seasons.length} seasons found.` : 'Selected.';
      if (fileGuess && fileGuess.episode) episode.value = fileGuess.episode;
      syncSeason();
      markShelf();
      loadEpisodes();
    } catch (e) {
      if (mine === seq) status.textContent = `${e.message} You can search again.`;
    }
  }

  function render(results) {
    list.replaceChildren();
    results.forEach((r) => {
      const li = document.createElement('li');
      li.className = 'lookup__item';
      li.setAttribute('role', 'option');
      const text = document.createElement('div');
      text.className = 'lookup__text';
      const name = document.createElement('span');
      name.className = 'lookup__name';
      name.textContent = r.title;
      const sub = document.createElement('span');
      sub.className = 'lookup__sub';
      sub.textContent = detail(r);
      text.append(name, sub);
      li.appendChild(text);
      li.addEventListener('mousedown', (e) => { e.preventDefault(); pick(r); });
      list.appendChild(li);
    });
    list.hidden = !results.length;
    search.setAttribute('aria-expanded', String(results.length > 0));
    if (!results.length) status.textContent = 'No anime found. Try another spelling.';
  }

  async function run() {
    const q = search.value.trim();
    if (q.length < 2) { hide(); status.textContent = idle; return; }
    const mine = ++seq;
    status.textContent = 'Searching...';
    try {
      const data = await getJson(`/new/anime/search?q=${encodeURIComponent(q)}`);
      if (mine !== seq) return;
      status.textContent = idle;
      render(data.results || []);
    } catch (e) {
      if (mine === seq) status.textContent = `${e.message} You can search again.`;
    }
  }

  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 250); });
  search.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hide();
    if (e.key === 'Enter' && !list.hidden) { e.preventDefault(); list.firstElementChild.dispatchEvent(new MouseEvent('mousedown', { cancelable: true })); }
  });
  search.addEventListener('blur', hide);
  season.addEventListener('change', syncSeason);
  episode.addEventListener('input', syncSeason);
})();
