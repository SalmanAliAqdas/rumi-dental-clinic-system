/* Only dashboard panels refresh; phone-search input and other forms remain intact. */
(() => {
  const panel = document.querySelector('#daily-panels');
  if (!panel) return;
  const deadline = Date.now() + Number(panel.dataset.expirySeconds) * 1000;
  const day = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Karachi', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  let refreshing = false;
  function expire() {
    panel.replaceChildren();
    window.location.replace('/login/');
  }
  async function tick() {
    if (Date.now() >= deadline) { expire(); return; }
    const stored = panel.querySelector('[data-business-date]');
    if (!stored || stored.dataset.businessDate === day() || refreshing) return;
    refreshing = true;
    // Remove yesterday's data before fetching, preserving the search form.
    panel.textContent = 'Pakistan date changed. Refreshing today and tasks…';
    try {
      const response = await fetch(panel.dataset.url, { credentials: 'same-origin', redirect: 'error', cache: 'no-store' });
      if (!response.ok || response.headers.get('X-Rumi-Panel') !== '1') { expire(); return; }
      const html = await response.text();
      if (Date.now() >= deadline) { expire(); return; }
      panel.innerHTML = html;
    } catch (_) {
      panel.textContent = 'Today could not be refreshed. ';
      const link = document.createElement('a');
      link.href = '/';
      link.textContent = 'Refresh today or sign in again';
      panel.append(link);
    } finally { refreshing = false; }
  }
  setInterval(tick, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  window.addEventListener('pageshow', tick);
})();
