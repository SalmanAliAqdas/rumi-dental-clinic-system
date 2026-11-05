/* Patient notes stay in this DOM and the authenticated server, never localStorage. */
(() => {
  const form = document.querySelector('#visit-editor');
  if (!form) return;
  const status = document.querySelector('#save-state');
  const revision = form.elements.namedItem('revision');
  let timer = null, pending = null, dirty = false, generation = 0, submitting = false;
  const csrf = () => {
    const cookie = document.cookie.split('; ').find(value => value.startsWith('csrftoken='));
    if (cookie) form.elements.namedItem('csrfmiddlewaretoken').value = decodeURIComponent(cookie.split('=').slice(1).join('='));
  };
  async function save() {
    if (pending || submitting || !dirty) return pending;
    csrf();
    const sent = generation;
    status.textContent = 'Saving…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    pending = (async () => {
      try {
        const response = await fetch(form.dataset.autosaveUrl, {method: 'POST', body: new FormData(form), credentials: 'same-origin', signal: controller.signal, headers: {'X-Requested-With': 'XMLHttpRequest'}});
        if (response.status === 401 || response.status === 403 || response.redirected) throw new Error('Session may have expired. Keep this tab open, sign in in another tab, then Retry draft save.');
        if (response.status === 409) throw new Error('Newer revision or completed visit. Keep your text here; open the latest visit in another tab and reconcile before saving.');
        if (!response.ok) throw new Error('Save failed. Check dates, clinician, medical review confirmation and tooth selections. Your text is retained here.');
        const result = await response.json();
        if (!result.saved || !Number.isInteger(result.revision)) throw new Error('Save was not confirmed. Your text is retained here.');
        revision.value = result.revision;
        if (generation === sent) {
          dirty = false;
          status.textContent = `Saved ${result.saved_at} · revision ${result.revision}`;
        } else {
          status.textContent = 'Saving newer changes…';
          timer = setTimeout(save, 500);
        }
      } catch (error) {
        status.textContent = `Failed — ${error.name === 'AbortError' ? 'Request timed out. Keep this tab and check the latest server revision before retrying.' : error.message}`;
      } finally {
        clearTimeout(timeout);
        pending = null;
      }
    })();
    return pending;
  }
  form.addEventListener('input', () => { generation += 1; dirty = true; clearTimeout(timer); timer = setTimeout(save, 900); });
  form.addEventListener('change', () => { generation += 1; dirty = true; clearTimeout(timer); timer = setTimeout(save, 900); });
  document.querySelector('#retry-save').addEventListener('click', () => { clearTimeout(timer); save(); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    clearTimeout(timer);
    if (pending) await pending;
    csrf();
    const data = new FormData(form);
    data.set('action', event.submitter?.value || 'save');
    submitting = true;
    const controls = Array.from(form.elements).filter(control => !control.disabled);
    controls.forEach(control => { control.disabled = true; });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    status.textContent = 'Saving…';
    let navigating = false;
    try {
      // Buttons named "action" can shadow the form.action DOM property.
      const response = await fetch(form.getAttribute('action') || window.location.href, {method: 'POST', body: data, credentials: 'same-origin', signal: controller.signal});
      const destination = new URL(response.url);
      if (response.status === 401 || response.status === 403 || destination.pathname.startsWith('/login/')) throw new Error('Session may have expired. Keep this tab open, sign in in another tab, then retry. Your text is retained here.');
      if (response.status === 409) throw new Error('A newer revision exists. Keep this text and reconcile with the latest visit in another tab.');
      if (response.ok && response.redirected && destination.origin === window.location.origin) {
        dirty = false;
        navigating = true;
        window.location.assign(destination.href);
        return;
      }
      const body = await response.text();
      const errors = Array.from(new DOMParser().parseFromString(body, 'text/html').querySelectorAll('.errorlist')).map(node => node.textContent.trim()).join(' ');
      throw new Error(errors || 'Save failed. Check required fields, dates and completed-work notes. Your text is retained here.');
    } catch (error) {
      dirty = true;
      status.textContent = `Failed — ${error.name === 'AbortError' ? 'Request timed out. Keep this tab and check the latest visit before retrying.' : error.message}`;
    } finally {
      clearTimeout(timeout);
      if (!navigating) {
        submitting = false;
        controls.forEach(control => { control.disabled = false; });
      }
    }
  });
  window.addEventListener('beforeunload', event => { if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; } });
})();
