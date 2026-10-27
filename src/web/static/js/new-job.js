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
