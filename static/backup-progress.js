(() => {
  const container = document.querySelector('#backup-progress');
  if (!container || !['queued', 'running'].includes(container.dataset.state)) return;
  const state = document.querySelector('#backup-state');
  const stage = document.querySelector('#backup-stage');
  async function poll() {
    try {
      const response = await fetch(container.dataset.url, {credentials: 'same-origin', redirect: 'error', cache: 'no-store'});
      if (response.status === 503) { stage.textContent = 'Coordinated snapshot write pause; retrying progress shortly.'; setTimeout(poll, 3000); return; }
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) throw new Error('session');
      const job = await response.json();
      state.textContent = job.status; stage.textContent = job.stage;
      if (['queued', 'running'].includes(job.status)) setTimeout(poll, 3000);
      else window.location.reload();
    } catch (_) {
      container.replaceChildren();
      const link = document.createElement('a'); link.href = '/backups/'; link.textContent = 'Progress unavailable. Sign in again or refresh the backup centre.'; container.append(link);
    }
  }
  setTimeout(poll, 1000);
})();
