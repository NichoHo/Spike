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

// From anime tab: search a title, then pick the season and episode. Each season is its own AniList entry with its own
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
  const detail = (s) => [s.format ? s.format.replace('_', ' ') : null, s.year, s.episodes ? `${s.episodes} episodes` : null]
    .filter(Boolean).join(' · ');

  function syncSeason() {
    const s = seasons.find((x) => String(x.id) === season.value);
    if (!s) return;
    if (s.episodes) episode.max = s.episodes; else episode.removeAttribute('max');
    if (!episode.value) episode.value = 1;
    if (s.episodes && Number(episode.value) > s.episodes) episode.value = s.episodes;
    epHelp.textContent = s.episodes ? `${s.episodes} episodes in this season.` : 'The episode count is not published yet.';
    label.value = `${s.title} episode ${episode.value}`;
  }

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
      syncSeason();
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
