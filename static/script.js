// Year in footer
document.getElementById('year').textContent = new Date().getFullYear();

/*  Modal (Alert Dialog) */
function openModal(id){
  document.getElementById('modalOverlay').classList.add('open');
  document.querySelectorAll('.modal').forEach(m => m.classList.remove('open'));
  document.querySelector(id).classList.add('open');
}
function closeModal(){
  document.getElementById('modalOverlay').classList.remove('open');
  document.querySelectorAll('.modal').forEach(m => m.classList.remove('open'));
}
document.addEventListener('click', (e)=>{
  const t = e.target;
  if (t.matches('[data-dialog-trigger]')) { e.preventDefault(); openModal(t.getAttribute('data-dialog-trigger')); }
  if (t.matches('#modalOverlay, [data-dialog-close]')) { closeModal(); }
});
document.addEventListener('keydown', (e)=>{ if (e.key === 'Escape') closeModal(); });

/*  Dropdown (demo) */
document.addEventListener('click', (e) => {
  const trigger = e.target.closest('[data-dropdown-toggle]');
  if (trigger) {
    const panel = document.querySelector(trigger.getAttribute('data-dropdown-toggle'));
    const open = panel.classList.contains('open');
    document.querySelectorAll('.dropdown-panel.open').forEach(p=>p.classList.remove('open'));
    document.querySelectorAll('[aria-expanded="true"][data-dropdown-toggle]').forEach(b=>b.setAttribute('aria-expanded','false'));
    panel.classList.toggle('open', !open);
    trigger.setAttribute('aria-expanded', String(!open));
    return;
  }
  if (!e.target.closest('.dropdown')) {
    document.querySelectorAll('.dropdown-panel.open').forEach(p=>p.classList.remove('open'));
    document.querySelectorAll('[aria-expanded="true"][data-dropdown-toggle]').forEach(b=>b.setAttribute('aria-expanded','false'));
  }
});

/* Context Menu (demo) */
const ctxOverlay = document.getElementById('contextOverlay');
const ctxPanel   = document.getElementById('contextPanel');
function closeContext() {
  ctxOverlay?.classList.remove('open');
  ctxPanel?.classList.remove('open');
}
document.addEventListener('contextmenu', (e) => {
  const target = e.target.closest('[data-context-target]');
  if (!target) return;
  e.preventDefault();
  ctxOverlay.classList.add('open');
  ctxPanel.classList.add('open');
  const x = e.clientX + 2, y = e.clientY + 2;
  ctxPanel.style.left = x + 'px';
  ctxPanel.style.top  = y + 'px';
});
document.addEventListener('click', (e)=>{
  if (e.target === ctxOverlay || !e.target.closest('#contextPanel')) closeContext();
});
document.addEventListener('keydown', (e)=>{ if (e.key === 'Escape') closeContext(); });

/* Drawer (demo)  */
function openDrawer(id){
  document.getElementById('drawerOverlay').classList.add('open');
  document.querySelector(id).classList.add('open');
}
function closeDrawer(){
  document.getElementById('drawerOverlay').classList.remove('open');
  document.querySelectorAll('.drawer.open').forEach(d=>d.classList.remove('open'));
}
document.addEventListener('click', (e)=>{
  const t = e.target;
  if (t.matches('[data-drawer-trigger]')) {
    e.preventDefault();
    openDrawer(t.getAttribute('data-drawer-trigger'));
  }
  if (t.matches('#drawerOverlay, [data-drawer-close]')) closeDrawer();
});



/* Tiny Toasts */
function toast(msg){
  const host = document.getElementById('toasts');
  if (!host) return;
  const node = document.createElement('div');
  node.className = 'toast';
  node.textContent = msg;
  host.appendChild(node);
  requestAnimationFrame(()=> node.classList.add('in'));
  setTimeout(()=> {
    node.classList.remove('in');
    setTimeout(()=> node.remove(), 200);
  }, 2400);
}

/*
   Ingestion Flow (Dashboard -> Upload -> Tags -> Metadata) */
(function () {
  const app = document.getElementById('ingestion-app');
  if (!app) return;

  // router
  const screens = [...app.querySelectorAll('.screen')];
  const steps = [...app.querySelectorAll('.ingest-step')];
  function show(screenName) {
    screens.forEach(s => s.classList.toggle('active', s.dataset.screen === screenName));
    steps.forEach(st => st.setAttribute('aria-current', st.dataset.step === screenName ? 'page' : 'false'));
    window.scrollTo({ top: app.offsetTop - 12, behavior: 'smooth' });
  }

  // Initial
  show('dashboard');

  //Dashboard search (local filter swap with LLM later)
  const docList = document.getElementById('docList');
  const searchInput = document.getElementById('docSearch');
  const searchBtn = document.getElementById('docSearchBtn');

  function filterCards(q) {
    const query = (q || '').trim().toLowerCase();
    const cards = [...docList.querySelectorAll('.doc-card')];
    cards.forEach(card => {
      const title = (card.dataset.title || card.querySelector('.doc-title')?.textContent || '').toLowerCase();
      const author = (card.dataset.author || '').toLowerCase();
      const matches = !query || title.includes(query) || author.includes(query);
      card.style.display = matches ? '' : 'none';
    });
  }
  searchInput?.addEventListener('input', () => filterCards(searchInput.value));
  searchBtn?.addEventListener('click', () => {
    filterCards(searchInput.value);
    toast('Searching documents…');
  });

  // Nav buttons
  app.querySelector('#btnGoUpload')?.addEventListener('click', () => show('upload'));
  app.querySelector('#backToDashboard')?.addEventListener('click', () => show('dashboard'));

  // Upload screen logic (with test mode)
  const dropzone = app.querySelector('#dropzone');
  const fileInput = app.querySelector('#fileInput');
  const browseBtn = app.querySelector('#browseBtn');
  const filePicked = app.querySelector('#filePicked');
  const toTagsBtn = app.querySelector('#toTags');
  const skipUploadCk = app.querySelector('#skipUpload');
  const testNote = app.querySelector('#testNote');

  function validateFile(file) {
    if (!file) return { ok: false, reason: 'No file selected' };
    const extOk = /\.(pdf|docx)$/i.test(file.name);
    const sizeOk = file.size <= 25 * 1024 * 1024; // 25MB
    if (!extOk) return { ok: false, reason: 'PDF or DOCX only' };
    if (!sizeOk) return { ok: false, reason: 'File too large (max 25MB)' };
    return { ok: true };
  }
  function setPickedText(text) {
    if (!filePicked) return;
    filePicked.hidden = false;
    filePicked.textContent = text;
  }
  function setPicked(file) {
    setPickedText(`Selected: ${file.name} (${Math.ceil(file.size/1024)} KB)`);
  }

  browseBtn?.addEventListener('click', () => fileInput?.click());
  fileInput?.addEventListener('change', (e) => {
    const f = e.target.files[0];
    const res = validateFile(f);
    if (!res.ok) { alert(res.reason); fileInput.value = ''; return; }
    setPicked(f);
  });

  ['dragenter','dragover'].forEach(evt => {
    dropzone?.addEventListener(evt, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropzone.classList.add('dragover');
    });
  });
  ['dragleave','drop'].forEach(evt => {
    dropzone?.addEventListener(evt, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropzone.classList.remove('dragover');
    });
  });
  dropzone?.addEventListener('drop', (e) => {
    const f = e.dataTransfer.files[0];
    if (!f) return;
    const res = validateFile(f);
    if (!res.ok) { alert(res.reason); return; }
    setPicked(f);
  });

  // Toggle test note
  skipUploadCk?.addEventListener('change', () => {
    testNote.hidden = !skipUploadCk.checked;
  });

  // Press Enter in any upload input -> continue
  ['#docTitle','#docAuthor','#docDate'].forEach(sel => {
    app.querySelector(sel)?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') toTagsBtn?.click();
    });
  });

  toTagsBtn?.addEventListener('click', () => {
    const title = /** @type {HTMLInputElement} */(app.querySelector('#docTitle'))?.value.trim();
    const skip = !!skipUploadCk?.checked;

    if (!title) { alert('Please enter a title.'); return; }

    if (!skip) {
      if (!filePicked || filePicked.hidden) { alert('Please choose a file to upload, or enable "Skip file (test mode)".'); return; }
    } else if (!filePicked || filePicked.hidden) {
      // Show a placeholder so downstream screens see something
      setPickedText('Selected: (skipped in test mode)');
    }

    show('tags');
  });

  // Tag Suggestions
  const suggestedTagsEl = app.querySelector('#suggestedTags');
  const manualTagInput = app.querySelector('#manualTag');
  const addTagBtn = app.querySelector('#addTagBtn');
  const acceptAllBtn = app.querySelector('#acceptAllTags');
  const backToUploadBtn = app.querySelector('#backToUpload');
  const toMetadataBtn = app.querySelector('#toMetadata');

  const tagState = {
    suggestions: ['#Policy', '#Budget', '#HR', '#Benefits'],
    accepted: new Set()
  };

  function ensureHash(tag) {
    const t = (tag || '').trim();
    if (!t) return '';
    return t.startsWith('#') ? t : `#${t}`;
  }

  function renderSuggestions() {
    suggestedTagsEl.innerHTML = '';
    tagState.suggestions.forEach(tag => {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.innerHTML = `<span>${tag}</span><span class="chip-x" title="Remove" aria-label="Remove tag">×</span>`;
      // Click label → accept
      chip.firstElementChild.addEventListener('click', () => {
        tagState.accepted.add(tag);
        chip.style.opacity = '.5';
      });
      // Remove from suggestion list
      chip.querySelector('.chip-x')?.addEventListener('click', () => {
        tagState.suggestions = tagState.suggestions.filter(t => t !== tag);
        tagState.accepted.delete(tag);
        renderSuggestions();
      });
      suggestedTagsEl.appendChild(chip);
    });
  }
  renderSuggestions();

  // Add manual tag (button or Enter key)
  function addManualTag() {
    const t = ensureHash(manualTagInput.value);
    if (!t) return;
    if (!tagState.suggestions.includes(t)) {
      tagState.suggestions.push(t);
      renderSuggestions();
      manualTagInput.value = '';
      manualTagInput.focus();
    }
  }
  addTagBtn?.addEventListener('click', addManualTag);
  manualTagInput?.addEventListener('keydown', (e)=>{ if (e.key === 'Enter') addManualTag(); });

  acceptAllBtn?.addEventListener('click', () => {
    tagState.suggestions.forEach(t => tagState.accepted.add(t));
    show('metadata');
    syncFinalTags();
  });

  backToUploadBtn?.addEventListener('click', () => show('upload'));
  toMetadataBtn?.addEventListener('click', () => {
    if (!tagState.accepted.size) {
      tagState.suggestions.forEach(t => tagState.accepted.add(t));
    }
    show('metadata');
    syncFinalTags();
  });

  //  Metadata
  const finalTagsEl = app.querySelector('#finalTags');
  const backToTagsBtn = app.querySelector('#backToTags');
  const submitBtn = app.querySelector('#submitRepo');

  function syncFinalTags() {
    finalTagsEl.innerHTML = '';
    [...tagState.accepted].forEach(tag => {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.innerHTML = `<span>${tag}</span><span class="chip-x" title="Remove" aria-label="Remove tag">×</span>`;
      chip.querySelector('.chip-x')?.addEventListener('click', () => {
        tagState.accepted.delete(tag);
        syncFinalTags();
      });
      finalTagsEl.appendChild(chip);
    });
  }

  backToTagsBtn?.addEventListener('click', () => show('tags'));

  // add a new document card to the Dashboard
  function appendNewDocCard({ title, author, updated, status }) {
    const card = document.createElement('article');
    card.className = 'doc-card';
    card.dataset.title = title;
    card.dataset.author = author || '';
    const badgeClass =
      status === 'Complete' ? 'badge-success' :
      status === 'Failed'   ? 'badge-danger'  : 'badge-warning';
    card.innerHTML = `
      <div class="doc-row">
        <div class="doc-title">${title}</div>
        <span class="badge ${badgeClass}">${status}</span>
      </div>
      <div class="doc-meta">
        <span>Author: ${author || '—'}</span>
        <span>Updated: ${updated}</span>
      </div>`;
    docList.prepend(card);
  }

  submitBtn?.addEventListener('click', () => {
    const classification = /** @type {HTMLSelectElement} */(app.querySelector('#classification'))?.value;
    const reviewer = /** @type {HTMLInputElement} */(app.querySelector('#reviewer'))?.value.trim();
    const title = /** @type {HTMLInputElement} */(app.querySelector('#docTitle'))?.value.trim();
    const author = /** @type {HTMLInputElement} */(app.querySelector('#docAuthor'))?.value.trim() || '—';
    const date   = /** @type {HTMLInputElement} */(app.querySelector('#docDate'))?.value || new Date().toISOString().slice(0,10);

    if (!title) { alert('Missing title.'); return; }
    if (!tagState.accepted.size) { alert('Please include at least one tag.'); return; }

    // Append to dashboard (simulated)
    appendNewDocCard({
      title,
      author,
      updated: date,
      status: 'In Progress'
    });

    // Show confirmation
    alert(`Submitted:
- Title: ${title}
- Tags: ${[...tagState.accepted].join(', ')}
- Classification: ${classification}
- Reviewer: ${reviewer || '—'}`);

    show('dashboard');
    toast('Submitted to repository');
  });
})();
