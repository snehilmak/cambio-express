/* Form-draft autosave.
 *
 * Pages opt in by giving their <form> a `data-draft-key="<unique>"`
 * attribute. While the user types we debounce-save form state to
 * localStorage under `db-draft:<key>`. On the next page load, if a
 * draft exists and is < 24h old, we surface a banner offering to
 * Restore or Discard. On form submit we clear the draft.
 *
 * Quiet-fail on quota / private mode — autosave is a nice-to-have,
 * never an error path. If validation fails server-side, the page
 * re-renders with the user's data (Flask form-state rendering), so
 * the data isn't lost even though the draft was cleared on submit;
 * the next keystroke re-establishes the draft.
 */
(function () {
  const form = document.querySelector('form[data-draft-key]');
  if (!form) return;

  const key = 'db-draft:' + form.dataset.draftKey;
  const TTL_MS = 24 * 60 * 60 * 1000;
  const SAVE_DEBOUNCE_MS = 500;

  // We persist visible inputs/selects/textareas plus hidden inputs
  // (hidden carries customer_id from the sender autocomplete, which
  // we want to round-trip on restore). Skip passwords, file inputs,
  // submits/buttons, and the CSRF-token slot if/when it lands.
  function namedFields() {
    return form.querySelectorAll(
      'input[name]:not([type=password]):not([type=submit]):not([type=button]):not([type=file]):not([name=csrf_token]),' +
      'select[name], textarea[name]'
    );
  }

  function snapshot() {
    const data = {};
    namedFields().forEach(el => {
      if (el.type === 'checkbox') {
        data[el.name] = el.checked ? '1' : '';
      } else if (el.type === 'radio') {
        if (el.checked) data[el.name] = el.value;
      } else {
        data[el.name] = el.value;
      }
    });
    return data;
  }

  function isEmpty(data) {
    return !Object.values(data).some(v => v !== '' && v != null);
  }

  function save() {
    try {
      const data = snapshot();
      if (isEmpty(data)) {
        localStorage.removeItem(key);
        return;
      }
      localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }));
    } catch (e) { /* quota / private mode — best-effort */ }
  }

  function clear() {
    try { localStorage.removeItem(key); } catch (e) {}
  }

  function load() {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !parsed.ts || (Date.now() - parsed.ts) > TTL_MS) {
        clear();
        return null;
      }
      return parsed;
    } catch (e) { return null; }
  }

  function restoreInto(data) {
    Object.entries(data).forEach(([name, value]) => {
      const el = form.querySelector('[name="' + cssEscape(name) + '"]');
      if (!el) return;
      if (el.type === 'checkbox') {
        el.checked = !!value;
      } else if (el.type === 'radio') {
        const match = form.querySelector('[name="' + cssEscape(name) + '"][value="' + cssEscape(value) + '"]');
        if (match) match.checked = true;
      } else {
        el.value = value;
      }
      // Fire change so any field with side-effect listeners (federal
      // tax auto-fill, country flag swap, etc.) reacts.
      el.dispatchEvent(new Event('input',  { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  function cssEscape(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_\-]/g, c => '\\' + c);
  }

  function relTime(ts) {
    const sec = Math.floor((Date.now() - ts) / 1000);
    if (sec < 60)    return 'a moment ago';
    if (sec < 3600)  return Math.floor(sec / 60) + ' minutes ago';
    if (sec < 86400) return Math.floor(sec / 3600) + ' hours ago';
    return new Date(ts).toLocaleString();
  }

  function showRestoreBanner(parsed) {
    const banner = document.createElement('div');
    banner.className = 'draft-banner';
    banner.setAttribute('role', 'status');
    banner.innerHTML =
      '<svg class="draft-banner__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
        '<polyline points="17 8 12 3 7 8"/>' +
        '<line x1="12" y1="3" x2="12" y2="15"/>' +
      '</svg>' +
      '<span class="draft-banner__text">' +
        'Unsaved draft from <strong class="draft-banner__when"></strong>. Pick up where you left off?' +
      '</span>' +
      '<button type="button" class="btn btn-primary btn-sm draft-banner__restore">Restore</button>' +
      '<button type="button" class="btn btn-outline btn-sm draft-banner__discard">Discard</button>';
    banner.querySelector('.draft-banner__when').textContent = relTime(parsed.ts);
    form.parentNode.insertBefore(banner, form);
    banner.querySelector('.draft-banner__restore').addEventListener('click', () => {
      restoreInto(parsed.data);
      banner.remove();
    });
    banner.querySelector('.draft-banner__discard').addEventListener('click', () => {
      clear();
      banner.remove();
    });
  }

  // Wire up autosave + restore banner.
  const existing = load();
  if (existing && !isEmpty(existing.data)) {
    showRestoreBanner(existing);
  }

  let saveTimer = null;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, SAVE_DEBOUNCE_MS);
  }
  namedFields().forEach(el => {
    el.addEventListener('input',  scheduleSave);
    el.addEventListener('change', scheduleSave);
  });

  // On submit: clear the draft. Synchronous so it persists across
  // the page nav even on slow networks.
  form.addEventListener('submit', clear);
})();
