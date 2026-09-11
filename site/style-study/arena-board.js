const referenceGrid = document.querySelector('#arena-grid');
const referenceStatus = document.querySelector('#arena-status');
const referenceDialog = document.querySelector('#arena-detail');
const choiceKey = 'specter-arena-reference-choices-v1';
let choices = {};
try { choices = JSON.parse(localStorage.getItem(choiceKey) || '{}'); } catch {}
if (!choices || typeof choices !== 'object' || Array.isArray(choices)) choices = {};
let references = [], filter = 'All';
function saveChoice(id, choice) {
  choices[id] = choices[id] === choice ? undefined : choice;
  try { localStorage.setItem(choiceKey, JSON.stringify(choices)); } catch {}
  renderReferences();
}
function openReference(ref) {
  document.querySelector('#arena-detail-image').src = ref.image;
  document.querySelector('#arena-detail-image').alt = ref.title;
  document.querySelector('#arena-detail-title').textContent = ref.title;
  document.querySelector('#arena-detail-observation').textContent = ref.observation;
  document.querySelector('#arena-detail-application').textContent = ref.application;
  document.querySelector('#arena-detail-source').href = ref.source;
  referenceDialog.showModal();
}
function renderReferences() {
  const visible = references.filter(r => filter === 'All' || (filter === 'Kept' ? choices[r.id] === 'keep' : r.category === filter));
  referenceGrid.replaceChildren();
  for (const ref of visible) {
    const article = document.createElement('article');
    article.className = 'arena-reference';
    article.dataset.choice = choices[ref.id] || '';
    const zoom = document.createElement('button');
    zoom.className = 'arena-image';
    zoom.setAttribute('aria-label', 'Enlarge ' + ref.title);
    const img = new Image(); img.src = ref.image; img.alt = ref.title; img.loading = 'lazy';
    img.addEventListener('error', () => { zoom.textContent = 'Preview unavailable — open reference details'; });
    zoom.append(img); zoom.addEventListener('click', () => openReference(ref)); article.append(zoom);
    for (const [tag, text, cls] of [['p', ref.category, 'eyebrow'], ['h3', ref.title, ''], ['p', ref.observation, ''], ['p', ref.application, 'arena-application']]) {
      const el = document.createElement(tag); el.textContent = text; el.className = cls; article.append(el);
    }
    const controls = document.createElement('div'); controls.className = 'arena-choice';
    for (const [value, label] of [['keep', 'Keep'], ['pass', 'Pass']]) {
      const button = document.createElement('button'); button.textContent = label;
      button.setAttribute('aria-label', `${label}: ${ref.title}`);
      button.setAttribute('aria-pressed', String(choices[ref.id] === value));
      button.addEventListener('click', () => { saveChoice(ref.id, value); referenceGrid.querySelector(`[aria-label="${label}: ${ref.title}"]`)?.focus(); });
      controls.append(button);
    }
    const link = document.createElement('a'); link.href = ref.source; link.textContent = 'Source ↗'; controls.append(link); article.append(controls); referenceGrid.append(article);
  }
  const kept = references.filter(r => choices[r.id] === 'keep').length;
  referenceStatus.textContent = `${visible.length} shown · ${kept} kept` + (!visible.length ? ' — mark an image Keep to collect it here.' : '');
}
document.querySelectorAll('[data-reference-filter]').forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.referenceFilter;
  document.querySelectorAll('[data-reference-filter]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
  renderReferences();
}));
document.querySelector('.arena-close').addEventListener('click', () => referenceDialog.close());
referenceDialog.addEventListener('click', e => { if(e.target === referenceDialog){ const r=referenceDialog.getBoundingClientRect(); if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)referenceDialog.close(); } });
fetch('arena-references.json').then(r => { if(!r.ok)throw Error(); return r.json(); }).then(data => { references = data; renderReferences(); }).catch(() => { referenceStatus.textContent = 'The reference board could not load. Reload to try again.'; });
