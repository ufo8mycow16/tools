/* Third Moon Audiobook Studio - the app (no build step, no libraries). */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const view = $('#view');
const audio = $('#audio');
const sample = $('#sample');

const EMOTIONS = ['', 'angry', 'crying', 'dramatic', 'fear', 'happy', 'sarcastic', 'surprised', 'whispering'];
const SOUNDS = ['', '[laugh]', '[chuckle]', '[gasp]', '[cough]', '[sigh]', '[groan]', '[sniff]', '[shush]', '[clear throat]'];

// ------------------------------------------------------------------------------------------------ helpers
async function api(method, path, body, extra = {}) {
  const opt = { method, headers: {} };
  if (body instanceof Blob || body instanceof ArrayBuffer) {
    opt.body = body;
    Object.assign(opt.headers, extra);
  } else if (body !== undefined) {
    opt.body = JSON.stringify(body);
    opt.headers['Content-Type'] = 'application/json';
  }
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `${r.status} ${r.statusText}`);
  return data;
}
const get = p => api('GET', p);
const post = (p, b = {}) => api('POST', p, b);
const patch = (p, b) => api('PATCH', p, b);
const del = p => api('DELETE', p);

function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}` : `${m}:${String(x).padStart(2, '0')}`;
}
function plural(n, w) { return `${(n || 0).toLocaleString()} ${w}${n === 1 ? '' : 's'}`; }
function fmtLong(s) {
  s = Math.round(s || 0);
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}
function hue(name) { let h = 0; for (const c of name || '') h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
function charColour(name) { return name ? `hsl(${hue(name)} 70% 66%)` : 'var(--faint)'; }
function initials(n) { return (n || '?').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase(); }

let toastTimer;
function toast(msg, err = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast show' + (err ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.className = 'toast', err ? 6000 : 3000);
}
async function attempt(fn, ok) {
  try { const r = await fn(); if (ok) toast(ok); return r; } catch (e) { toast(e.message, true); }
}
function modal(html, onReady) {
  $('#modalCard').innerHTML = html;
  $('#modal').classList.remove('hidden');
  if (onReady) onReady($('#modalCard'));
}
function closeModal() { $('#modal').classList.add('hidden'); }
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });

function coverHTML(b, progress = true) {
  const pct = Math.round((b.progress || 0) * 100);
  return `<div class="cover">${b.cover_url ? `<img src="${b.cover_url}" alt="" loading="lazy">` : `<div class="ph">${esc(b.title)}</div>`}
    ${progress && pct ? `<div class="stripe"><i style="width:${pct}%"></i></div>` : ''}</div>`;
}
function statusPill(b) {
  if (b.status === 'generating') return '<span class="pill gold">Making audio</span>';
  if (b.chapters_total && b.chapters_done === b.chapters_total) return '<span class="pill green">Ready to listen</span>';
  if (b.chapters_done) return `<span class="pill blue">${b.chapters_done}/${b.chapters_total} chapters</span>`;
  if (b.analysed) return '<span class="pill blue">Cast ready</span>';
  return '<span class="pill">New</span>';
}

// ------------------------------------------------------------------------------------------------ router
const routes = [
  [/^#?\/?$/, viewLibrary, 'library'],
  [/^#\/book\/(\d+)(?:\/(\w+))?$/, viewBook, 'library'],
  [/^#\/listen\/(\d+)$/, viewListen, 'library'],
  [/^#\/voices$/, viewVoices, 'voices'],
  [/^#\/words$/, viewWords, 'words'],
  [/^#\/queue$/, viewQueue, 'queue'],
  [/^#\/settings$/, viewSettings, 'settings'],
];
let currentView = null;
async function route() {
  const h = location.hash || '#/';
  for (const [rx, fn, nav] of routes) {
    const m = h.match(rx);
    if (m) {
      $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.nav === nav));
      currentView = fn.name;
      view.innerHTML = '';
      try { await fn(...m.slice(1)); } catch (e) { view.innerHTML = `<div class="card bad">${esc(e.message)}</div>`; }
      updateMini();
      window.scrollTo(0, 0);
      return;
    }
  }
  location.hash = '#/';
}
window.addEventListener('hashchange', route);

// ------------------------------------------------------------------------------------------------ library
async function viewLibrary() {
  const books = await get('/api/books');
  const last = books.find(b => b.opened && b.chapters_done);
  view.innerHTML = `
    ${last ? `<section class="hero">
      <a href="#/listen/${last.id}">${coverHTML(last)}</a>
      <div>
        <div class="muted">CONTINUE LISTENING</div>
        <h2>${esc(last.title)}</h2>
        <div class="sub">${esc(last.author)}</div>
        <div class="bar" style="margin:14px 0 6px;max-width:420px"><i style="width:${Math.round(last.progress * 100)}%"></i></div>
        <div class="muted">${fmtLong(last.listened)} of ${fmtLong(last.duration)}</div>
        <div class="row" style="margin-top:14px"><a class="btn gold" href="#/listen/${last.id}">&#9654; Carry on</a>
        <a class="btn ghost" href="#/book/${last.id}">Book details</a></div>
      </div></section>` : ''}
    <div class="row between"><h1>Library</h1>
      <div class="row">
        <button class="btn" id="pasteBtn">&#128203; Paste text</button>
        <button class="btn" id="urlBtn">&#127760; Web page</button>
        <label class="btn gold">&#10010; Add a book<input type="file" id="file" accept=".epub,.txt,.md,.html,.htm" hidden multiple></label>
      </div>
    </div>
    <div class="drop" id="drop">Drop EPUB books here (or .txt / .html). Gemma reads each one and finds the cast.</div>
    <div class="books">${books.map(b => `
      <div class="book" data-id="${b.id}">${coverHTML(b)}
        <div class="t">${esc(b.title)}</div><div class="a">${esc(b.author)}</div>
        <div style="margin-top:6px">${statusPill(b)}</div></div>`).join('') ||
      '<p class="sub">No books yet. Drop an EPUB above to start.</p>'}</div>`;
  $$('.book').forEach(el => el.onclick = () => location.hash = `#/book/${el.dataset.id}`);
  $('#file').onchange = e => uploadBooks([...e.target.files]);
  const drop = $('#drop');
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => uploadBooks([...e.dataTransfer.files]));
  $('#pasteBtn').onclick = pasteDialog;
  $('#urlBtn').onclick = urlDialog;
}

async function uploadBooks(files) {
  for (const f of files) {
    toast(`Reading ${f.name}...`);
    const b = await attempt(() => api('POST', '/api/books/import', f, { 'X-Filename': encodeURIComponent(f.name) }));
    if (b) toast(`Added "${b.title}". Gemma is reading it now.`);
  }
  route();
}

function pasteDialog() {
  modal(`<h2>Listen to some text</h2>
    <label class="field"><span>Title</span><input type="text" id="pt" placeholder="Something to listen to"></label>
    <label class="field" style="margin-top:10px"><span>Text</span><textarea id="px" placeholder="Paste anything - an article, a chapter, notes..."></textarea></label>
    <label class="switch" style="margin-top:10px"><input type="checkbox" id="pn" checked> Make the audio straight away</label>
    <div class="row" style="margin-top:16px;justify-content:flex-end"><button class="btn ghost" onclick="closeModal()">Cancel</button>
    <button class="btn gold" id="pgo">Add</button></div>`, card => {
    $('#pgo', card).onclick = async () => {
      const b = await attempt(() => post('/api/books/text', { title: $('#pt').value, text: $('#px').value, listen_now: $('#pn').checked }));
      if (b) { closeModal(); location.hash = `#/book/${b.id}`; }
    };
  });
}
function urlDialog() {
  modal(`<h2>Listen to a web page</h2>
    <label class="field"><span>Web address</span><input type="url" id="uu" placeholder="https://..."></label>
    <label class="switch" style="margin-top:10px"><input type="checkbox" id="un" checked> Make the audio straight away</label>
    <div class="row" style="margin-top:16px;justify-content:flex-end"><button class="btn ghost" onclick="closeModal()">Cancel</button>
    <button class="btn gold" id="ugo">Fetch it</button></div>`, card => {
    $('#ugo', card).onclick = async () => {
      toast('Fetching the page...');
      const b = await attempt(() => post('/api/books/url', { url: $('#uu').value, listen_now: $('#un').checked }));
      if (b) { closeModal(); location.hash = `#/book/${b.id}`; }
    };
  });
}

// ------------------------------------------------------------------------------------------------ book page
let voicesCache = null;
async function getVoices(force) {
  if (!voicesCache || force) voicesCache = await get('/api/voices');
  return voicesCache;
}
function voiceOptions(vs, sel, blank = '— narrator —') {
  return `<option value="">${blank}</option>` + vs.map(v =>
    `<option value="${v.key}" ${v.key === sel ? 'selected' : ''}>${esc(v.name)}${v.gender ? ' (' + v.gender[0].toUpperCase() + ')' : ''}${v.missing ? ' — missing!' : ''}</option>`).join('');
}

async function viewBook(id, tab = 'overview') {
  const b = await get(`/api/books/${id}`);
  const vs = await getVoices();
  const done = b.chapters.filter(c => c.include && c.status === 'done').length;
  const incl = b.chapters.filter(c => c.include).length;
  view.innerHTML = `
    <div class="bookhead">
      ${coverHTML(b)}
      <div class="stack">
        <div><h1 style="margin:0">${esc(b.title)}</h1><div class="sub">${esc(b.author)}${b.series ? ' · ' + esc(b.series) : ''}</div></div>
        <div class="row">${statusPill(b)}
          <span class="pill">${plural(incl, 'chapter')} · ${plural(b.words, 'word')}</span>
          ${b.duration ? `<span class="pill">${fmtLong(b.duration)} of audio</span>` : `<span class="pill">about ${fmtLong((b.words || 0) / 150 * 60)} to listen</span>`}
          ${b.analysed ? `<span class="pill ${b.analysis_method === 'rules' ? '' : 'gold'}">Cast by ${b.analysis_method === 'rules' ? 'rules' : 'Gemma'}</span>` : ''}
        </div>
        ${b.description ? `<div class="desc" id="desc">${esc(b.description)}</div>` : ''}
        <div class="row">
          <a class="btn gold" href="#/listen/${b.id}" ${done ? '' : 'style="opacity:.6"'}>&#9654; Listen</a>
          <button class="btn" id="genAll">&#127908; Make the audio${done && done < incl ? ` (${incl - done} left)` : ''}</button>
          <button class="btn" id="analyse">&#129504; ${b.analysed ? 'Re-read with Gemma' : 'Read the book with Gemma'}</button>
          <button class="btn" id="export">&#128230; Export audiobook</button>
          <button class="btn red ghost" id="stop">Stop</button>
        </div>
      </div>
    </div>
    <div class="subtabs">${[['overview', 'Chapters'], ['cast', `Cast (${b.characters.filter(c => !c.hidden).length})`], ['script', 'Script'],
      ['bookmarks', `Bookmarks (${b.bookmarks.length})`], ['words', 'Pronunciation'], ['details', 'Details']]
      .map(([k, l]) => `<button data-tab="${k}" class="${k === tab ? 'on' : ''}">${l}</button>`).join('')}</div>
    <div id="tab"></div>`;
  $$('.subtabs button').forEach(bt => bt.onclick = () => history.replaceState(null, '', `#/book/${id}/${bt.dataset.tab}`) || viewBook(id, bt.dataset.tab));
  const d = $('#desc'); if (d) d.onclick = () => d.classList.toggle('open');
  $('#genAll').onclick = () => attempt(() => post(`/api/books/${id}/generate`), 'Queued. Watch it on the Queue page - you can listen as chapters finish.');
  $('#analyse').onclick = () => attempt(() => post(`/api/books/${id}/analyse`), 'Gemma is reading the book.');
  $('#stop').onclick = () => attempt(() => post(`/api/books/${id}/stop`), 'Stopped.');
  $('#export').onclick = () => exportDialog(b);
  const tabEl = $('#tab');
  if (tab === 'overview') tabChapters(b, tabEl);
  if (tab === 'cast') tabCast(b, vs, tabEl);
  if (tab === 'script') tabScript(b, vs, tabEl);
  if (tab === 'bookmarks') tabBookmarks(b, tabEl);
  if (tab === 'words') wordsEditor(tabEl, b.id);
  if (tab === 'details') tabDetails(b, tabEl);
}

function tabChapters(b, el) {
  el.innerHTML = `<div class="card chapters" style="padding:6px">
    ${b.chapters.map(c => {
      const pct = c.lines ? Math.round(c.made / c.lines * 100) : 0;
      return `<div class="ch ${c.include ? '' : 'off'}" data-id="${c.id}">
        <div class="n">${c.idx + 1}</div>
        <div><div><b>${esc(c.title)}</b> ${c.kind !== 'chapter' ? `<span class="pill">${c.kind === 'front' ? 'front matter' : 'back matter'}</span>` : ''}</div>
          <div class="muted">${plural(c.words, 'word')} · ${plural(c.dialogue, 'line')} of dialogue
          ${c.status === 'done' ? ` · <span class="ok">${fmtTime(c.duration)}</span>` : c.made ? ` · ${pct}% made` : ''}</div>
          ${c.status !== 'done' && c.made ? `<div class="bar" style="margin-top:6px;max-width:260px"><i style="width:${pct}%"></i></div>` : ''}
          ${c.summary ? `<div class="sub" style="margin-top:6px;font-size:14px">${esc(c.summary)}</div>` : ''}
        </div>
        <div class="row hide-sm">
          ${c.status === 'done' ? `<a class="btn small" href="#/listen/${b.id}" data-play="${c.idx}">&#9654; Play</a>` :
            `<button class="btn small" data-gen="${c.id}" ${c.include ? '' : 'disabled'}>Make</button>`}
          <button class="btn small ghost" data-sum="${c.id}" title="Gemma summary">Summary</button>
        </div>
        <label class="switch" title="Include in the audiobook"><input type="checkbox" data-inc="${c.id}" ${c.include ? 'checked' : ''}></label>
      </div>`;
    }).join('')}</div>`;
  $$('[data-inc]', el).forEach(i => i.onchange = () => attempt(() => patch(`/api/chapters/${i.dataset.inc}`, { include: i.checked })).then(() => viewBook(b.id, 'overview')));
  $$('[data-gen]', el).forEach(bt => bt.onclick = () => attempt(() => post(`/api/books/${b.id}/generate`, { chapters: [+bt.dataset.gen] }), 'Chapter queued.'));
  $$('[data-sum]', el).forEach(bt => bt.onclick = () => attempt(() => post(`/api/chapters/${bt.dataset.sum}/summary`), 'Gemma is summarising it.'));
  $$('[data-play]', el).forEach(a => a.onclick = () => { pendingChapter = +a.dataset.play; });
}

function tabCast(b, vs, el) {
  const chars = b.characters.filter(c => !c.hidden);
  el.innerHTML = `
    <div class="card narrator" style="margin-bottom:16px">
      <div class="row between"><div><div class="panel-title">Narrator</div><div class="sub">Reads everything that isn't dialogue, and any line nobody's sure about.</div></div>
        <div class="row" style="min-width:280px"><select id="narr">${voiceOptions(vs, b.narrator_voice, '— pick a voice —')}</select>
        <button class="icon" data-sample="${esc(b.narrator_voice)}" title="Hear it">&#9654;</button></div></div>
    </div>
    <div class="row between" style="margin-bottom:12px">
      <div class="sub">${b.unassigned ? `<span class="bad">${b.unassigned} lines of dialogue have no speaker yet</span> - the narrator reads them.` : 'Every line of dialogue has a speaker.'}</div>
      <div class="row"><button class="btn small" id="addChar">&#10010; Add character</button>
      <button class="btn small ghost" id="rules">Re-run the rules</button></div>
    </div>
    <div class="cast">${chars.map(c => `
      <div class="card who" data-id="${c.id}">
        <div class="avatar" style="background:${charColour(c.name)}">${initials(c.name)}</div>
        <div class="stack" style="min-width:0">
          <div class="row between"><div style="min-width:0"><div class="name">${esc(c.name)}</div>
            <div class="al">${plural(c.lines, 'line')}${c.gender ? ' · ' + c.gender : ''}${c.aliases.length ? ' · also ' + esc(c.aliases.slice(0, 4).join(', ')) : ''}</div></div>
            <button class="icon" data-edit="${c.id}" title="Edit">&#9998;</button></div>
          ${c.description ? `<div class="muted">${esc(c.description)}</div>` : ''}
          <div class="row"><select data-voice="${c.id}" class="grow" style="width:auto">${voiceOptions(vs, c.voice)}</select>
            <button class="icon" data-sample="${esc(c.voice || b.narrator_voice)}" title="Hear the voice">&#9654;</button></div>
          <button class="btn small ghost" data-lines="${c.id}">See their lines</button>
        </div>
      </div>`).join('')}</div>
    ${b.characters.some(c => c.hidden) ? `<p class="muted" style="margin-top:14px">Hidden: ${b.characters.filter(c => c.hidden).map(c => `<a href="#" data-unhide="${c.id}">${esc(c.name)}</a>`).join(', ')}</p>` : ''}`;
  $('#narr').onchange = e => attempt(() => patch(`/api/books/${b.id}`, { narrator_voice: e.target.value }), 'Narrator set.');
  $$('[data-voice]', el).forEach(s => s.onchange = () => attempt(() => patch(`/api/characters/${s.dataset.voice}`, { voice: s.value }), 'Voice set. Lines already made will be redone next time you make the audio.'));
  $$('[data-sample]', el).forEach(bt => bt.onclick = () => playVoice(bt.dataset.sample, bt));
  $$('[data-lines]', el).forEach(bt => bt.onclick = () => showLines(b, +bt.dataset.lines));
  $$('[data-edit]', el).forEach(bt => bt.onclick = () => editCharacter(b, b.characters.find(c => c.id === +bt.dataset.edit)));
  $$('[data-unhide]', el).forEach(a => a.onclick = e => { e.preventDefault(); attempt(() => patch(`/api/characters/${a.dataset.unhide}`, { hidden: 0 })).then(() => viewBook(b.id, 'cast')); });
  $('#addChar').onclick = () => {
    const name = prompt('Character name');
    if (name) attempt(() => post(`/api/books/${b.id}/characters`, { name })).then(() => viewBook(b.id, 'cast'));
  };
  $('#rules').onclick = () => attempt(() => post(`/api/books/${b.id}/rules`), 'Done.').then(() => viewBook(b.id, 'cast'));
}

async function showLines(b, cid) {
  const lines = await get(`/api/characters/${cid}/lines`);
  const c = b.characters.find(x => x.id === cid);
  modal(`<h2>${esc(c.name)}'s lines</h2>
    <div class="stack">${lines.map(l => `<div><span class="muted">${esc(l.chapter_title)}</span><div style="font-family:var(--serif)">${esc(l.display)}</div></div>`).join('') || '<p class="sub">No lines yet.</p>'}</div>
    <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn" onclick="closeModal()">Close</button></div>`);
}

function editCharacter(b, c) {
  const others = b.characters.filter(x => x.id !== c.id);
  modal(`<h2>${esc(c.name)}</h2>
    <div class="stack">
      <label class="field"><span>Name</span><input type="text" id="cn" value="${esc(c.name)}"></label>
      <label class="field"><span>Other names (comma separated)</span><input type="text" id="ca" value="${esc(c.aliases.join(', '))}"></label>
      <label class="field"><span>Gender</span><select id="cg"><option value="">unknown</option><option ${c.gender === 'male' ? 'selected' : ''}>male</option><option ${c.gender === 'female' ? 'selected' : ''}>female</option></select></label>
      <label class="field"><span>Description</span><input type="text" id="cd" value="${esc(c.description)}"></label>
      <label class="field"><span>Same person as... (merge)</span><select id="cm"><option value="">—</option>${others.map(o => `<option value="${o.id}">${esc(o.name)}</option>`).join('')}</select></label>
    </div>
    <div class="row between" style="margin-top:18px">
      <div class="row"><button class="btn red small" id="cdel">Remove</button><button class="btn small ghost" id="chide">Hide</button></div>
      <div class="row"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn gold" id="csave">Save</button></div>
    </div>`, card => {
    $('#csave', card).onclick = async () => {
      if ($('#cm').value) {
        await attempt(() => post(`/api/characters/${c.id}/merge`, { into: +$('#cm').value }), 'Merged.');
      } else {
        await attempt(() => patch(`/api/characters/${c.id}`, { name: $('#cn').value, aliases: $('#ca').value.split(','), gender: $('#cg').value, description: $('#cd').value }), 'Saved.');
      }
      closeModal(); viewBook(b.id, 'cast');
    };
    $('#cdel', card).onclick = async () => { if (confirm(`Remove ${c.name}? Their lines go back to the narrator.`)) { await attempt(() => del(`/api/characters/${c.id}`)); closeModal(); viewBook(b.id, 'cast'); } };
    $('#chide', card).onclick = async () => { await attempt(() => patch(`/api/characters/${c.id}`, { hidden: 1 })); closeModal(); viewBook(b.id, 'cast'); };
  });
}

async function playVoice(key, btn) {
  if (!key) return toast('Pick a voice first.', true);
  const vs = await getVoices(true);
  const v = vs.find(x => x.key === key);
  if (!v) return toast('That voice has gone missing.', true);
  if (v.preview_url) { sample.src = v.preview_url; sample.play(); return; }
  toast(`Making a sample of ${v.name} (the first one takes a moment while Chatterbox wakes up)...`);
  const { job } = await post(`/api/voices/${key}/preview`);
  waitJob(job, () => getVoices(true).then(vs2 => {
    const v2 = vs2.find(x => x.key === key);
    if (v2 && v2.preview_url) { sample.src = v2.preview_url + '?t=' + Date.now(); sample.play(); }
  }));
}
function waitJob(id, done) {
  const t = setInterval(async () => {
    const st = await get('/api/jobs');
    const j = st.jobs.find(x => x.id === id);
    if (!j || ['done', 'failed', 'cancelled'].includes(j.status)) {
      clearInterval(t);
      if (j && j.status === 'failed') toast(j.error || 'That didn\'t work.', true); else done && done(j);
    }
  }, 1500);
}

async function tabScript(b, vs, el, chapterId) {
  const chs = b.chapters.filter(c => c.include);
  const cid = chapterId || (chs[0] && chs[0].id);
  if (!cid) { el.innerHTML = '<p class="sub">No chapters included.</p>'; return; }
  const ch = await get(`/api/chapters/${cid}`);
  const names = b.characters.map(c => c.name);
  let lastPara = -1;
  el.innerHTML = `
    <div class="row between" style="margin-bottom:12px">
      <select id="chSel" style="max-width:420px">${chs.map(c => `<option value="${c.id}" ${c.id === cid ? 'selected' : ''}>${c.idx + 1}. ${esc(c.title)}</option>`).join('')}</select>
      <div class="muted">Click a speaker to change it. Changes are remade next time you make the audio.</div>
    </div>
    <div class="card script">${ch.segments.map(s => {
      const gap = s.para !== lastPara && lastPara !== -1 ? '<div class="para-gap"></div>' : '';
      lastPara = s.para;
      if (s.kind === 'break') return gap + '<div class="seg break">* * *</div>';
      if (s.kind === 'heading') return gap + `<div class="seg heading"><span></span><span>${esc(s.display)}</span><span></span></div>`;
      const who = s.kind === 'dialogue' ? (s.speaker || '') : 'Narrator';
      return gap + `<div class="seg ${s.kind}" data-id="${s.id}">
        <div class="who2">${s.kind === 'dialogue' ? `<span class="chip ${who ? '' : 'unk'}" style="${who ? `background:${charColour(who)};color:#111` : ''}" data-who="${s.id}">${esc(who || 'who?')}</span>` : '<span class="muted">narrator</span>'}</div>
        <div>${esc(s.display)}${s.emotion ? `<span class="tagchip">[${s.emotion}]</span>` : ''}${s.sound ? `<span class="tagchip">${esc(s.sound)}</span>` : ''}
          ${s.speaker_source && s.kind === 'dialogue' ? `<span class="muted" title="How the speaker was found"> · ${s.speaker_source}</span>` : ''}</div>
        <div class="row" style="gap:4px">${s.status === 'done' ? `<button class="icon" style="width:30px;height:30px;font-size:12px" data-hear="${s.id}" title="Hear this line">&#9654;</button>` : ''}
          <button class="icon" style="width:30px;height:30px;font-size:12px" data-line="${s.id}" title="Edit / redo">&#9998;</button></div>
      </div>`;
    }).join('')}</div>`;
  $('#chSel').onchange = e => tabScript(b, vs, el, +e.target.value);
  $$('[data-hear]', el).forEach(bt => bt.onclick = () => { sample.src = `/files/segment/${bt.dataset.hear}.flac?t=${Date.now()}`; sample.play(); });
  $$('[data-who]', el).forEach(chip => chip.onclick = () => editLine(b, vs, ch.segments.find(s => s.id === +chip.dataset.who), names, () => tabScript(b, vs, el, cid)));
  $$('[data-line]', el).forEach(bt => bt.onclick = () => editLine(b, vs, ch.segments.find(s => s.id === +bt.dataset.line), names, () => tabScript(b, vs, el, cid)));
}

function editLine(b, vs, s, names, after) {
  modal(`<h2>Line</h2>
    <p style="font-family:var(--serif);font-size:18px">${esc(s.display)}</p>
    <div class="stack">
      <label class="field"><span>Spoken text (what Chatterbox reads - fix spellings here)</span><textarea id="lt" style="min-height:80px">${esc(s.text)}</textarea></label>
      ${s.kind === 'dialogue' ? `
      <label class="field"><span>Speaker</span><input type="text" id="ls" list="castList" value="${esc(s.speaker)}" placeholder="who says it?">
        <datalist id="castList">${names.map(n => `<option value="${esc(n)}">`).join('')}<option value="Narrator"></datalist></label>
      <label class="switch"><input type="checkbox" id="lw" checked> Same speaker for the whole speech</label>
      <div class="row"><label class="field grow"><span>How it's said</span><select id="le">${EMOTIONS.map(e => `<option value="${e}" ${e === s.emotion ? 'selected' : ''}>${e || 'normal'}</option>`).join('')}</select></label>
      <label class="field grow"><span>Sound first</span><select id="lx">${SOUNDS.map(e => `<option value="${e}" ${e === s.sound ? 'selected' : ''}>${e || 'none'}</option>`).join('')}</select></label></div>` : ''}
      <label class="field"><span>Voice just for this line (optional)</span><select id="lv">${voiceOptions(vs, s.voice, '— usual voice —')}</select></label>
    </div>
    <div class="row between" style="margin-top:18px">
      <button class="btn" id="lredo">&#8635; Save and redo this line now</button>
      <div class="row"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn gold" id="lsave">Save</button></div>
    </div>`, card => {
    const save = () => {
      const body = { text: $('#lt').value, voice: $('#lv').value };
      if (s.kind === 'dialogue') Object.assign(body, { speaker: $('#ls').value.trim(), emotion: $('#le').value, sound: $('#lx').value, whole_quote: $('#lw').checked });
      return patch(`/api/segments/${s.id}`, body);
    };
    $('#lsave', card).onclick = async () => { await attempt(save, 'Saved.'); closeModal(); after(); };
    $('#lredo', card).onclick = async () => {
      await attempt(save);
      const r = await attempt(() => post(`/api/segments/${s.id}/regenerate`), 'Making a new take...');
      closeModal();
      if (r) waitJob(r.job, () => { toast('New take ready.'); after(); });
    };
  });
}

function tabBookmarks(b, el) {
  el.innerHTML = b.bookmarks.length ? `<div class="card">${b.bookmarks.map(m => {
    const ch = b.chapters.find(c => c.idx === m.chapter_idx);
    return `<div class="row between" style="padding:10px 0;border-bottom:1px solid var(--line)">
      <div><b>${esc(m.label || 'Bookmark')}</b> <span class="muted">${esc(ch ? ch.title : '')} · ${fmtTime(m.time)}</span>
      ${m.note ? `<div class="sub">${esc(m.note)}</div>` : ''}</div>
      <div class="row"><a class="btn small" href="#/listen/${b.id}" data-jump="${m.chapter_idx}:${m.time}">&#9654; Go</a>
      <button class="btn small red" data-bdel="${m.id}">Delete</button></div></div>`;
  }).join('')}</div>` : '<p class="sub">No bookmarks yet - add them while you listen.</p>';
  $$('[data-jump]', el).forEach(a => a.onclick = () => { const [c, t] = a.dataset.jump.split(':'); pendingChapter = +c; pendingTime = +t; });
  $$('[data-bdel]', el).forEach(bt => bt.onclick = () => attempt(() => del(`/api/bookmarks/${bt.dataset.bdel}`)).then(() => viewBook(b.id, 'bookmarks')));
}

async function tabDetails(b, el) {
  const exports = await get(`/api/books/${b.id}/exports`);
  el.innerHTML = `<div class="settings-grid">
    <div class="card stack">
      <div class="panel-title">Book details</div>
      <label class="field"><span>Title</span><input type="text" id="dt" value="${esc(b.title)}"></label>
      <label class="field"><span>Author</span><input type="text" id="da" value="${esc(b.author)}"></label>
      <label class="field"><span>Series</span><input type="text" id="ds" value="${esc(b.series)}"></label>
      <div class="row"><button class="btn gold" id="dsave">Save</button><button class="btn red" id="ddel">Delete book</button></div>
    </div>
    <div class="card stack">
      <div class="panel-title">Exported audiobooks</div>
      ${exports.map(x => `<div class="row between"><div><b>${esc(x.file)}</b><div class="muted">${(x.size / 1048576).toFixed(1)} MB</div></div>
        <a class="btn small" href="${x.url}" download>&#11015; Download</a></div>`).join('') || '<p class="sub">Nothing exported yet.</p>'}
      <p class="muted">On your phone: open this page over Wi-Fi and tap Download - the .m4b goes straight into your audiobook app.</p>
    </div></div>`;
  $('#dsave').onclick = () => attempt(() => patch(`/api/books/${b.id}`, { title: $('#dt').value, author: $('#da').value, series: $('#ds').value }), 'Saved.');
  $('#ddel').onclick = async () => {
    if (!confirm(`Delete "${b.title}" and all its audio? Exported audiobooks are kept.`)) return;
    await attempt(() => del(`/api/books/${b.id}`), 'Deleted.');
    if (player.book && player.book.id === b.id) stopPlayer();
    location.hash = '#/';
  };
}

function exportDialog(b) {
  modal(`<h2>Export the audiobook</h2>
    <p class="sub">Every included chapter needs its audio made first.</p>
    <div class="stack">
      <label class="card" style="display:block;cursor:pointer"><input type="radio" name="fmt" value="m4b" checked>
        <b> .m4b audiobook</b><div class="muted">One file with chapter marks and the cover - the proper audiobook format for phone apps (Smart AudioBook Player, Voice, BookPlayer).</div></label>
      <label class="card" style="display:block;cursor:pointer"><input type="radio" name="fmt" value="mp3">
        <b> MP3 per chapter</b><div class="muted">Plays anywhere, including the car's USB. Comes as a folder and a zip.</div></label>
    </div>
    <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn gold" id="xgo">Export</button></div>`, card => {
    $('#xgo', card).onclick = async () => {
      const fmt = $('input[name=fmt]:checked', card).value;
      const r = await attempt(() => post(`/api/books/${b.id}/export`, { format: fmt }));
      closeModal();
      if (r) { toast('Exporting...'); waitJob(r.job, () => { toast('Exported - it\'s on the Details tab.'); }); }
    };
  });
}

// ------------------------------------------------------------------------------------------------ the player
const player = { book: null, chapters: [], idx: 0, chapter: null, segs: [], cur: -1, speed: 1, sleep: null, sleepEnd: false, follow: true, lastSave: 0, listenedTick: 0 };
let pendingChapter = null, pendingTime = null;
const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3];

async function viewListen(id) {
  id = +id;
  const b = await get(`/api/books/${id}`);
  const playable = b.chapters.filter(c => c.include);
  if (!player.book || player.book.id !== id) {
    stopPlayer();
    player.book = b;
    player.speed = b.speed || +localStorage.getItem('speed') || 1;
  } else player.book = b;
  player.chapters = playable;
  let idx = pendingChapter ?? (player.chapter ? player.idx : b.pos_chapter);
  let t = pendingTime ?? (player.chapter && pendingChapter === null ? audio.currentTime : b.pos_time);
  pendingChapter = pendingTime = null;
  if (!playable.find(c => c.idx === idx)) idx = (playable[0] || {}).idx || 0;

  const fs = +localStorage.getItem('fontSize') || 20;
  const light = localStorage.getItem('readerLight') === '1';
  view.innerHTML = `
  <div class="player">
    <aside class="pside">
      <a href="#/book/${b.id}">${coverHTML(b)}</a>
      <div class="now"><div class="bt">${esc(b.title)}</div><div class="ct" id="pChapter"></div></div>
      <div class="seek"><input type="range" id="pSeek" min="0" max="1000" value="0">
        <div class="times"><span id="pPos">0:00</span><span id="pLeft"></span></div></div>
      <div class="controls">
        <button class="icon" id="pPrevCh" title="Previous chapter">&#9198;</button>
        <button class="icon skip" id="pBack" title="Back">&#8634;<small>15</small></button>
        <button class="play" id="pPlay" title="Play / pause (space)">&#9654;</button>
        <button class="icon skip" id="pFwd" title="Forward">&#8635;<small>15</small></button>
        <button class="icon" id="pNextCh" title="Next chapter">&#9197;</button>
      </div>
      <div class="row" style="justify-content:center;gap:8px">
        <button class="btn small" id="pPrevS" title="Previous sentence (←)">&#8592; sentence</button>
        <button class="btn small" id="pNextS" title="Next sentence (→)">sentence &#8594;</button>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="speedrow"><span class="muted">Speed</span><input type="range" id="pSpeed" min="0.5" max="4" step="0.05" value="${player.speed}"><span class="speedval" id="pSpeedV"></span></div>
        <div class="presets" id="pPresets">${SPEEDS.map(s => `<button data-s="${s}">${s}×</button>`).join('')}</div>
      </div>
      <div class="row" style="margin-top:12px;gap:8px">
        <button class="btn small" id="pBm">&#9733; Bookmark</button>
        <select id="pSleep" style="width:auto"><option value="">&#9790; Sleep timer</option><option value="5">5 min</option><option value="15">15 min</option><option value="30">30 min</option><option value="45">45 min</option><option value="60">1 hour</option><option value="end">End of chapter</option></select>
        <span class="muted" id="pSleepLeft"></span>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="row between"><div class="panel-title" style="margin:0">Chapters</div><button class="btn small ghost" id="pRecap">Story so far</button></div>
        <div class="side-list" id="pChList"></div>
      </div>
    </aside>
    <section>
      <div class="readerbar">
        <input type="search" id="pSearch" placeholder="Search the book..." style="max-width:260px">
        <span class="grow"></span>
        <label class="switch"><input type="checkbox" id="pFollow" ${player.follow ? 'checked' : ''}> Follow along</label>
        <button class="btn small" id="pSmaller">A−</button><button class="btn small" id="pBigger">A+</button>
        <button class="btn small" id="pTheme">${light ? '&#9790; Dark' : '&#9788; Paper'}</button>
      </div>
      <div id="pSearchRes"></div>
      <div class="reader ${light ? 'light' : ''}" id="reader" style="--fs:${fs}px"></div>
    </section>
  </div>`;
  renderChapterList();
  await loadChapter(idx, t, false);
  bindPlayer();
  setSpeed(player.speed);
}

function renderChapterList() {
  const el = $('#pChList');
  if (!el) return;
  el.innerHTML = player.chapters.map(c => `<div class="it ${c.idx === player.idx ? 'on' : ''}" data-ci="${c.idx}">
    <span class="muted" style="min-width:22px">${c.idx + 1}</span><span class="grow">${esc(c.title)}</span>
    <span class="muted">${c.status === 'done' ? fmtTime(c.duration) : '—'}</span></div>`).join('');
  $$('[data-ci]', el).forEach(it => it.onclick = () => loadChapter(+it.dataset.ci, 0, true));
}

async function loadChapter(idx, time = 0, autoplay = false) {
  const meta = player.chapters.find(c => c.idx === idx);
  if (!meta) return;
  const ch = await get(`/api/chapters/${meta.id}`);
  player.idx = idx;
  player.chapter = ch;
  player.segs = ch.segments;
  player.cur = -1;
  const pc = $('#pChapter'); if (pc) pc.textContent = ch.title;
  renderChapterList();
  renderReader();
  if (ch.audio_url) {
    if (!audio.src.endsWith(ch.audio_url)) audio.src = ch.audio_url;
    const go = () => { audio.currentTime = Math.min(time || 0, (audio.duration || 1e9) - 0.5); applySpeed(); if (autoplay) audio.play(); };
    if (audio.readyState >= 1) go(); else audio.addEventListener('loadedmetadata', go, { once: true });
  } else {
    audio.removeAttribute('src'); audio.load();
    const r = $('#reader');
    if (r) r.insertAdjacentHTML('afterbegin', `<div class="card" style="font-family:var(--sans);font-size:15px;margin-bottom:20px">
      This chapter's audio isn't made yet. <button class="btn small gold" id="makeThis">Make it now</button>
      <span class="muted"> - you can read along with the text meanwhile.</span></div>`);
    const mb = $('#makeThis'); if (mb) mb.onclick = () => attempt(() => post(`/api/books/${player.book.id}/generate`, { chapters: [ch.id] }), 'Queued - it starts playing here when it\'s ready.').then(() => waitForChapter(ch.id));
  }
  setupMediaSession();
  savePos(true);
  updateMini();
}

function waitForChapter(cid) {
  const t = setInterval(async () => {
    const ch = await get(`/api/chapters/${cid}`);
    if (ch.status === 'done') {
      clearInterval(t);
      if (player.chapter && player.chapter.id === cid) {
        const meta = player.chapters.find(c => c.id === cid); if (meta) { meta.status = 'done'; meta.duration = ch.duration; }
        loadChapter(player.idx, 0, true);
      }
    }
  }, 4000);
}

function renderReader() {
  const r = $('#reader');
  if (!r) return;
  const bms = (player.book.bookmarks || []).filter(m => m.chapter_idx === player.idx);
  const bmSeg = new Set(bms.map(m => m.segment_id));
  let html = '', para = -1, open = false;
  for (let i = 0; i < player.segs.length; i++) {
    const s = player.segs[i];
    if (s.para !== para) {
      if (open) html += '</p>';
      open = false;
      para = s.para;
      if (s.kind === 'heading') { html += `<div class="h s" data-i="${i}">${esc(s.display)}</div>`; continue; }
      if (s.kind === 'break') { html += '<div class="brk">* * *</div>'; continue; }
      html += '<p>'; open = true;
    }
    if (s.kind === 'heading' || s.kind === 'break') continue;
    const words = esc(s.display).split(/(\s+)/).map(w => /\S/.test(w) ? `<span class="w">${w}</span>` : w).join('');
    html += `<span class="s" data-i="${i}">${words}</span>${bmSeg.has(s.id) ? '<span class="bm">&#9733;</span>' : ''} `;
  }
  if (open) html += '</p>';
  r.innerHTML = html;
  r.onclick = e => {
    const s = e.target.closest('.s');
    if (!s) return;
    const seg = player.segs[+s.dataset.i];
    if (player.chapter.audio_url) { audio.currentTime = seg.start + 0.01; audio.play(); }
  };
}

function segAt(t) {
  const segs = player.segs;
  let lo = 0, hi = segs.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segs[mid].start <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  // skip the zero-length breaks
  while (ans > 0 && segs[ans].kind === 'break') ans--;
  return ans;
}

function highlight() {
  if (!player.chapter || !player.segs.length) return;
  const t = audio.currentTime;
  const i = segAt(t);
  const r = $('#reader');
  if (i !== player.cur) {
    if (r) {
      $$('.s.cur', r).forEach(e => e.classList.remove('cur'));
      const el = r.querySelector(`.s[data-i="${i}"]`);
      if (el) {
        el.classList.add('cur');
        if (player.follow && !audio.paused) {
          const rect = el.getBoundingClientRect();
          if (rect.top < 90 || rect.bottom > innerHeight - 120) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
      }
    }
    player.cur = i;
  }
  // word by word inside the sentence (spread over its length by characters)
  if (r && i >= 0) {
    const s = player.segs[i];
    const el = r.querySelector(`.s[data-i="${i}"]`);
    if (el && s.duration) {
      const frac = Math.min(1, Math.max(0, (t - s.start) / s.duration));
      const ws = $$('.w', el);
      const total = ws.reduce((a, w) => a + w.textContent.length + 1, 0);
      let acc = 0, target = frac * total, on = 0;
      for (let k = 0; k < ws.length; k++) { acc += ws[k].textContent.length + 1; if (acc >= target) { on = k; break; } on = k; }
      ws.forEach((w, k) => w.classList.toggle('on', k === on));
    }
  }
}

function bindPlayer() {
  $('#pPlay').onclick = togglePlay;
  $('#pBack').onclick = () => audio.currentTime = Math.max(0, audio.currentTime - 15);
  $('#pFwd').onclick = () => audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15);
  $('#pPrevCh').onclick = () => jumpChapter(-1);
  $('#pNextCh').onclick = () => jumpChapter(1);
  $('#pPrevS').onclick = () => jumpSentence(-1);
  $('#pNextS').onclick = () => jumpSentence(1);
  $('#pSeek').oninput = e => { if (audio.duration) audio.currentTime = e.target.value / 1000 * audio.duration; };
  $('#pSpeed').oninput = e => setSpeed(+e.target.value);
  $$('#pPresets button').forEach(b => b.onclick = () => setSpeed(+b.dataset.s));
  $('#pFollow').onchange = e => player.follow = e.target.checked;
  $('#pBigger').onclick = () => fontSize(2);
  $('#pSmaller').onclick = () => fontSize(-2);
  $('#pTheme').onclick = () => { const l = localStorage.getItem('readerLight') === '1' ? '0' : '1'; localStorage.setItem('readerLight', l); $('#reader').classList.toggle('light', l === '1'); $('#pTheme').innerHTML = l === '1' ? '&#9790; Dark' : '&#9788; Paper'; };
  $('#pBm').onclick = addBookmark;
  $('#pSleep').onchange = e => setSleep(e.target.value);
  $('#pRecap').onclick = recap;
  let st;
  $('#pSearch').oninput = e => { clearTimeout(st); st = setTimeout(() => search(e.target.value), 300); };
  updatePlayButton();
}

function fontSize(d) {
  const r = $('#reader');
  const v = Math.max(14, Math.min(34, (+localStorage.getItem('fontSize') || 20) + d));
  localStorage.setItem('fontSize', v);
  r.style.setProperty('--fs', v + 'px');
}

async function search(q) {
  const el = $('#pSearchRes');
  if (!q || q.length < 2) { el.innerHTML = ''; return; }
  const res = await get(`/api/books/${player.book.id}/search?q=${encodeURIComponent(q)}`);
  el.innerHTML = `<div class="card side-list" style="margin-bottom:12px">${res.map(r => `<div class="it" data-c="${r.chapter_idx}" data-t="${r.start}">
    <span class="muted" style="min-width:110px">${esc(r.chapter_title)}</span><span>${esc(r.display)}</span></div>`).join('') || '<div class="muted">Nothing found.</div>'}</div>`;
  $$('[data-c]', el).forEach(it => it.onclick = () => { el.innerHTML = ''; $('#pSearch').value = ''; loadChapter(+it.dataset.c, +it.dataset.t, true); });
}

function togglePlay() {
  if (!player.chapter || !player.chapter.audio_url) return toast('This chapter has no audio yet.', true);
  if (audio.paused) audio.play(); else audio.pause();
}
function jumpChapter(d) {
  const pos = player.chapters.findIndex(c => c.idx === player.idx);
  const next = player.chapters[pos + d];
  if (next) loadChapter(next.idx, 0, !audio.paused || d > 0);
}
function jumpSentence(d) {
  let i = segAt(audio.currentTime) + d;
  while (player.segs[i] && player.segs[i].kind === 'break') i += d;
  const s = player.segs[i];
  if (s) audio.currentTime = s.start + 0.01;
}
function setSpeed(s) {
  player.speed = Math.round(s * 100) / 100;
  localStorage.setItem('speed', player.speed);
  applySpeed();
  const v = $('#pSpeedV'); if (v) v.textContent = player.speed.toFixed(2).replace(/0$/, '') + '×';
  const r = $('#pSpeed'); if (r) r.value = player.speed;
  $$('#pPresets button').forEach(b => b.classList.toggle('on', +b.dataset.s === player.speed));
  if (player.book) patch(`/api/books/${player.book.id}`, { speed: player.speed }).catch(() => {});
}
function applySpeed() { audio.playbackRate = player.speed; audio.preservesPitch = true; }

function setSleep(v) {
  clearTimeout(player.sleep); player.sleep = null; player.sleepEnd = false;
  const lab = $('#pSleepLeft');
  if (!v) { if (lab) lab.textContent = ''; return; }
  if (v === 'end') { player.sleepEnd = true; if (lab) lab.textContent = 'stops at the chapter end'; return; }
  const until = Date.now() + v * 60000;
  const tick = () => {
    const left = until - Date.now();
    if (left <= 0) { fadeOutAndPause(); if (lab) lab.textContent = ''; $('#pSleep') && ($('#pSleep').value = ''); return; }
    if (lab) lab.textContent = fmtTime(left / 1000) + ' left';
    player.sleep = setTimeout(tick, 1000);
  };
  tick();
}
function fadeOutAndPause() {
  let v = 1;
  const t = setInterval(() => { v -= 0.05; audio.volume = Math.max(0, v); if (v <= 0) { clearInterval(t); audio.pause(); audio.volume = 1; } }, 150);
}

async function addBookmark() {
  const i = Math.max(0, segAt(audio.currentTime));
  const s = player.segs[i] || {};
  modal(`<h2>Bookmark</h2>
    <p style="font-family:var(--serif)">${esc(s.display || '')}</p>
    <label class="field"><span>Label</span><input type="text" id="bl" value="${esc((s.display || '').slice(0, 50))}"></label>
    <label class="field" style="margin-top:10px"><span>Note</span><textarea id="bn" style="min-height:80px" placeholder="Anything to remember..."></textarea></label>
    <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn gold" id="bsave">Save</button></div>`, card => {
    $('#bsave', card).onclick = async () => {
      const m = await attempt(() => post('/api/bookmarks', { book_id: player.book.id, chapter_idx: player.idx, time: audio.currentTime, segment_id: s.id, label: $('#bl').value, note: $('#bn').value }), 'Bookmarked.');
      if (m) { player.book.bookmarks.push(m); renderReader(); player.cur = -1; highlight(); }
      closeModal();
    };
  });
}

async function recap() {
  toast('Gemma is writing the story so far...');
  const r = await attempt(() => post(`/api/books/${player.book.id}/recap`, { upto: Math.max(0, player.idx - 1) }));
  if (!r) return;
  waitJob(r.job, async () => {
    const b = await get(`/api/books/${player.book.id}`);
    modal(`<h2>The story so far</h2><div class="recap">${esc(b.recap).replace(/\n/g, '<br>')}</div>
      <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn gold" onclick="closeModal()">Carry on</button></div>`);
  });
}

function updatePlayButton() {
  const b = $('#pPlay'); if (b) b.innerHTML = audio.paused ? '&#9654;' : '&#10074;&#10074;';
  const m = $('#miniPlay'); if (m) m.innerHTML = audio.paused ? '&#9654;' : '&#10074;&#10074;';
}

function savePos(force) {
  if (!player.book) return;
  const now = Date.now();
  if (!force && now - player.lastSave < 5000) return;
  player.lastSave = now;
  patch(`/api/books/${player.book.id}`, { pos_chapter: player.idx, pos_time: audio.currentTime || 0 }).catch(() => {});
}

function stopPlayer() {
  audio.pause();
  audio.removeAttribute('src');
  player.book = null; player.chapter = null; player.segs = [];
  updateMini();
}

audio.addEventListener('timeupdate', () => {
  const seek = $('#pSeek');
  if (seek && audio.duration) seek.value = audio.currentTime / audio.duration * 1000;
  const pos = $('#pPos'); if (pos) pos.textContent = fmtTime(audio.currentTime);
  const left = $('#pLeft'); if (left && audio.duration) left.textContent = '-' + fmtTime((audio.duration - audio.currentTime) / player.speed);
  const mb = $('#miniBar'); if (mb && audio.duration) mb.style.width = (audio.currentTime / audio.duration * 100) + '%';
  savePos();
  if (!audio.paused) {
    const n = Date.now();
    if (player.listenedTick && n - player.listenedTick > 30000) { post('/api/listened', { seconds: (n - player.listenedTick) / 1000 }).catch(() => {}); player.listenedTick = n; }
    if (!player.listenedTick) player.listenedTick = n;
  }
});
audio.addEventListener('play', () => { updatePlayButton(); loop(); if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'playing'; });
audio.addEventListener('pause', () => { updatePlayButton(); savePos(true); player.listenedTick = 0; if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'paused'; });
audio.addEventListener('ended', () => {
  if (player.sleepEnd) { player.sleepEnd = false; const s = $('#pSleep'); if (s) s.value = ''; const l = $('#pSleepLeft'); if (l) l.textContent = ''; return; }
  const pos = player.chapters.findIndex(c => c.idx === player.idx);
  const next = player.chapters[pos + 1];
  if (next && next.status === 'done') loadChapter(next.idx, 0, true);
  else if (next) toast('The next chapter is still being made.');
  else toast('The end. 🖖');
});
function loop() { highlight(); if (!audio.paused) requestAnimationFrame(loop); }

function setupMediaSession() {
  if (!('mediaSession' in navigator) || !player.book) return;
  const b = player.book;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: player.chapter ? player.chapter.title : b.title, artist: b.author, album: b.title,
    artwork: b.cover_url ? [{ src: b.cover_url, sizes: '512x512' }] : [],
  });
  const h = (a, f) => { try { navigator.mediaSession.setActionHandler(a, f); } catch (e) {} };
  h('play', () => audio.play()); h('pause', () => audio.pause());
  h('seekbackward', () => audio.currentTime = Math.max(0, audio.currentTime - 15));
  h('seekforward', () => audio.currentTime += 15);
  h('previoustrack', () => jumpChapter(-1)); h('nexttrack', () => jumpChapter(1));
  h('seekto', d => audio.currentTime = d.seekTime);
}

document.addEventListener('keydown', e => {
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || !player.chapter) return;
  if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
  else if (e.code === 'ArrowLeft') { e.preventDefault(); e.shiftKey ? audio.currentTime -= 15 : jumpSentence(-1); }
  else if (e.code === 'ArrowRight') { e.preventDefault(); e.shiftKey ? audio.currentTime += 15 : jumpSentence(1); }
  else if (e.key === ']') setSpeed(Math.min(4, player.speed + 0.25));
  else if (e.key === '[') setSpeed(Math.max(0.5, player.speed - 0.25));
  else if (e.key === 'b') addBookmark();
});

function updateMini() {
  const show = player.book && player.chapter && player.chapter.audio_url && currentView !== 'viewListen';
  $('#mini').classList.toggle('hidden', !show);
  if (!show) return;
  $('#miniCover').src = player.book.cover_url || '/icon.svg';
  $('#miniTitle').textContent = player.book.title;
  $('#miniChapter').textContent = player.chapter.title;
  $('#miniOpen').href = `#/listen/${player.book.id}`;
  updatePlayButton();
}
$('#miniPlay').onclick = togglePlay;

// ------------------------------------------------------------------------------------------------ voices
async function viewVoices() {
  const vs = await getVoices(true);
  const st = await get('/api/settings');
  view.innerHTML = `
    <div class="row between"><h1>Voices</h1>
      <label class="btn gold">&#10010; Add a voice<input type="file" id="vfile" accept="audio/*,.voc" hidden multiple></label></div>
    <p class="sub">From <b>${esc(st.reference_voices)}</b> (read only) and voices added here. A clean 10-20 second clip of one person talking, no music, works best.</p>
    <div class="voices">${vs.map(v => `
      <div class="card voice">
        <div class="row between"><div class="vn">${v.favourite ? '&#9733; ' : ''}${esc(v.name)}</div><span class="pill">${v.origin}</span></div>
        <div class="muted">${v.gender || 'gender not set'}${v.used_by.length ? ' · voices ' + esc(v.used_by.slice(0, 4).join(', ')) : ''}</div>
        ${v.missing ? '<div class="bad">The file has gone missing.</div>' : ''}
        <div class="wave">${Array.from({ length: 36 }, (_, i) => `<i style="height:${20 + (Math.sin(i * 1.7 + hue(v.key)) + 1) * 40}%"></i>`).join('')}</div>
        <div class="row">
          <button class="btn small" data-ref="${v.key}">&#9654; Original clip</button>
          <button class="btn small" data-prev="${v.key}">&#127908; ${v.preview_url ? 'Hear sample' : 'Make sample'}</button>
          <button class="icon" style="width:32px;height:32px" data-vedit="${v.key}">&#9998;</button>
        </div>
      </div>`).join('') || '<p class="sub">No voices found. Check the Reference Voices folder in Settings.</p>'}</div>`;
  $$('[data-ref]').forEach(b => b.onclick = () => { sample.src = `/files/voice/${b.dataset.ref}/reference`; sample.play(); });
  $$('[data-prev]').forEach(b => b.onclick = () => playVoice(b.dataset.prev, b));
  $$('[data-vedit]').forEach(b => b.onclick = () => editVoice(vs.find(v => v.key === b.dataset.vedit)));
  $('#vfile').onchange = async e => {
    for (const f of e.target.files) await attempt(() => api('POST', '/api/voices/upload', f, { 'X-Filename': encodeURIComponent(f.name) }), `Added ${f.name}`);
    viewVoices();
  };
}
function editVoice(v) {
  modal(`<h2>${esc(v.name)}</h2><div class="stack">
    <label class="field"><span>Name</span><input type="text" id="vn" value="${esc(v.name)}"></label>
    <label class="field"><span>Gender</span><select id="vg"><option value="">not set</option><option ${v.gender === 'male' ? 'selected' : ''}>male</option><option ${v.gender === 'female' ? 'selected' : ''}>female</option></select></label>
    <label class="field"><span>Notes</span><input type="text" id="vno" value="${esc(v.notes)}"></label>
    <label class="switch"><input type="checkbox" id="vf" ${v.favourite ? 'checked' : ''}> Favourite (top of the lists)</label>
    <label class="field"><span>Test it with your own words</span><input type="text" id="vt" placeholder="Beam me up..."></label></div>
    <div class="row between" style="margin-top:16px"><button class="btn" id="vtry">&#127908; Say it</button>
    <div class="row"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn gold" id="vsave">Save</button></div></div>`, card => {
    $('#vsave', card).onclick = async () => { await attempt(() => patch(`/api/voices/${v.key}`, { name: $('#vn').value, gender: $('#vg').value, notes: $('#vno').value, favourite: $('#vf').checked ? 1 : 0 }), 'Saved.'); closeModal(); viewVoices(); };
    $('#vtry', card).onclick = async () => {
      const text = $('#vt').value.trim(); if (!text) return toast('Type something to say first.', true);
      const r = await attempt(() => post(`/api/voices/${v.key}/preview`, { text }), 'Making it...');
      if (r) waitJob(r.job, async () => { const vs = await getVoices(true); const x = vs.find(y => y.key === v.key); sample.src = x.preview_url + '?t=' + Date.now(); sample.play(); });
    };
  });
}

// ------------------------------------------------------------------------------------------------ pronunciation
async function viewWords() {
  view.innerHTML = '<h1>Pronunciation</h1><p class="sub">How tricky words are said, for every book. Each book has its own list on its Pronunciation tab too.</p><div id="words"></div>';
  wordsEditor($('#words'), 0);
}
async function wordsEditor(el, bookId) {
  const rows = await get(`/api/pronunciations?book=${bookId}`);
  el.innerHTML = `<div class="card">
    <div class="row" style="margin-bottom:12px">
      <input type="text" id="wp" placeholder="Word as written (e.g. T'Pau)" style="max-width:260px">
      <input type="text" id="wr" placeholder="Say it as (e.g. Tee Pow)" style="max-width:260px">
      <button class="btn gold" id="wadd">Add${bookId ? ' for this book' : ''}</button>
      ${bookId ? '<span class="muted">Words for every book are on the Pronunciation page.</span>' : ''}
    </div>
    <table class="words"><tr><th>Written</th><th>Said as</th><th>Whole word</th><th>On</th><th>Where</th><th></th></tr>
    ${rows.map(r => `<tr><td><b>${esc(r.pattern)}</b></td><td>${esc(r.replacement)}</td>
      <td><input type="checkbox" data-ww="${r.id}" ${r.whole_word ? 'checked' : ''}></td>
      <td><label class="switch"><input type="checkbox" data-wo="${r.id}" ${r.enabled ? 'checked' : ''}></label></td>
      <td class="muted">${r.book_id ? 'this book' : 'every book'}</td>
      <td><button class="btn small red" data-wd="${r.id}">&#10005;</button></td></tr>`).join('')}</table></div>`;
  $('#wadd').onclick = async () => {
    if (!$('#wp').value.trim()) return;
    await attempt(() => post('/api/pronunciations', { book_id: bookId, pattern: $('#wp').value.trim(), replacement: $('#wr').value.trim() }), 'Added.');
    wordsEditor(el, bookId);
  };
  $$('[data-ww]', el).forEach(c => c.onchange = () => patch(`/api/pronunciations/${c.dataset.ww}`, { whole_word: c.checked ? 1 : 0 }));
  $$('[data-wo]', el).forEach(c => c.onchange = () => patch(`/api/pronunciations/${c.dataset.wo}`, { enabled: c.checked ? 1 : 0 }));
  $$('[data-wd]', el).forEach(b => b.onclick = () => attempt(() => del(`/api/pronunciations/${b.dataset.wd}`)).then(() => wordsEditor(el, bookId)));
}

// ------------------------------------------------------------------------------------------------ queue
async function viewQueue() {
  view.innerHTML = '<div class="row between"><h1>Queue</h1><div class="row" id="qctl"></div></div><div class="card" id="qjobs"></div><h2 style="margin-top:22px">Log</h2><div class="log" id="qlog"></div>';
  await refreshQueue();
}
const JOB_NAMES = { analyse: 'Reading the book', generate: 'Making audio', segment: 'Redoing a line', preview: 'Voice sample', export: 'Exporting', summary: 'Gemma summary' };
async function refreshQueue(st) {
  st = st || await get('/api/jobs');
  const el = $('#qjobs');
  if (!el) return;
  $('#qctl').innerHTML = `<span class="pill ${st.engine.loaded ? 'green' : ''}">Chatterbox ${st.engine.loaded ? 'loaded (' + st.engine.device + ')' : 'asleep'}</span>
    <button class="btn small" id="qpause">${st.paused ? '&#9654; Resume queue' : '&#10074;&#10074; Pause queue'}</button>`;
  $('#qpause').onclick = () => attempt(() => post('/api/queue/pause', { on: !st.paused })).then(() => refreshQueue());
  el.innerHTML = st.jobs.map(j => `<div class="job">
    <div><b>${JOB_NAMES[j.kind] || j.kind}</b> <span class="sub">${esc(j.book_title)}</span>
      <div class="muted">${esc(j.message || '')}${j.status === 'running' && st.eta && j.kind === 'generate' ? ' · about ' + fmtLong(st.eta) + ' to go' : ''}</div>
      ${j.error ? `<div class="bad">${esc(j.error)}</div>` : ''}
      ${j.status === 'running' ? `<div class="bar" style="margin-top:8px"><i style="width:${Math.round(j.progress * 100)}%"></i></div>` : ''}</div>
    <div class="row"><span class="pill ${{ running: 'gold', done: 'green', failed: 'red', queued: 'blue' }[j.status] || ''}">${j.status}</span>
      ${['queued', 'running'].includes(j.status) ? `<button class="btn small red" data-cancel="${j.id}">Cancel</button>` : ''}</div>
  </div>`).join('') || '<p class="sub">Nothing in the queue.</p>';
  $$('[data-cancel]', el).forEach(b => b.onclick = () => attempt(() => post(`/api/jobs/${b.dataset.cancel}/cancel`)).then(() => refreshQueue()));
  $('#qlog').textContent = st.log.map(l => new Date(l.t * 1000).toLocaleTimeString() + '  ' + l.msg).join('\n');
}

// ------------------------------------------------------------------------------------------------ settings
async function viewSettings() {
  const [s, st, stats] = await Promise.all([get('/api/settings'), get('/api/status'), get('/api/stats')]);
  const f = (k, label, type = 'text', extra = '') => `<label class="field"><span>${label}</span><input type="${type}" data-k="${k}" value="${esc(s[k])}" ${extra}></label>`;
  const sw = (k, label) => `<label class="switch"><input type="checkbox" data-k="${k}" ${s[k] ? 'checked' : ''}> ${label}</label>`;
  view.innerHTML = `<h1>Settings</h1>
    <div class="status-grid" style="margin-bottom:18px">
      <div class="card"><div class="panel-title">Gemma</div>${st.gemma.ok ? (st.gemma.model_ready ? `<span class="ok">&#10004; ${esc(s.ollama_model)} is ready</span>` :
        `<span class="bad">Ollama is up, but ${esc(s.ollama_model)} isn't there.</span><div class="muted">Has: ${esc(st.gemma.models.join(', ') || 'nothing')}</div>`) :
        `<span class="bad">Not answering</span><div class="muted">${esc(st.gemma.error)}</div>`}</div>
      <div class="card"><div class="panel-title">Chatterbox</div>${st.chatterbox_venv_ok ? '<span class="ok">&#10004; install found</span>' : '<span class="bad">venv not found</span>'}
        <div class="muted">${st.engine.loaded ? 'Loaded on ' + st.engine.device : 'Loads when it\'s first needed'}</div></div>
      <div class="card"><div class="panel-title">ffmpeg</div>${st.ffmpeg ? '<span class="ok">&#10004; found</span>' : '<span class="bad">not found - audio can\'t be built</span>'}</div>
      <div class="card"><div class="panel-title">Reference voices</div>${st.reference_folder_ok ? '<span class="ok">&#10004; folder found</span>' : '<span class="bad">folder not found</span>'}</div>
    </div>
    ${st.lan.length ? `<div class="card" style="margin-bottom:18px"><div class="panel-title">On your phone</div>
      <div class="sub">Same Wi-Fi, open this in Chrome, then "Add to Home screen":</div>${st.lan.map(u => `<div class="big-url">${esc(u)}</div>`).join('')}</div>` : ''}
    <div class="settings-grid">
      <div class="card stack"><div class="panel-title">Folders</div>
        ${f('chatterbox_root', 'Chatterbox Turbo folder')}${f('reference_voices', 'Reference Voices folder')}
        ${f('voices_dir', 'Voices added in the app')}${f('library_dir', 'Library (audio is kept here)')}${f('export_dir', 'Exported audiobooks')}</div>
      <div class="card stack"><div class="panel-title">Gemma (Ollama)</div>
        ${sw('use_ollama', 'Let Gemma read the books')}${f('ollama_url', 'Ollama address')}${f('ollama_model', 'Model')}
        ${f('ollama_context', 'Context size', 'number')}${sw('unload_ollama_after_analysis', 'Free the graphics card when she\'s done')}</div>
      <div class="card stack"><div class="panel-title">Chatterbox Turbo</div>
        <label class="field"><span>Device</span><select data-k="device">${['auto', 'cuda', 'cpu'].map(d => `<option ${s.device === d ? 'selected' : ''}>${d}</option>`).join('')}</select></label>
        ${f('temperature', 'Temperature', 'number', 'step="0.05"')}${f('top_p', 'Top p', 'number', 'step="0.01"')}
        ${f('top_k', 'Top k', 'number')}${f('repetition_penalty', 'Repetition penalty', 'number', 'step="0.05"')}
        ${f('max_chunk_chars', 'Longest piece read in one go (characters)', 'number')}
        ${sw('use_emotion_tags', 'Emotion tags on dialogue ([angry], [whispering]...)')}
        ${sw('use_sound_tags', 'Sounds when the book says so ([laugh], [sigh]...)')}
        ${sw('narration_tag', 'Turbo\'s [narration] tag on the narrator')}</div>
      <div class="card stack"><div class="panel-title">Pauses (ms)</div>
        ${f('gap_sentence', 'Between sentences', 'number')}${f('gap_speaker_change', 'When the speaker changes', 'number')}
        ${f('gap_paragraph', 'Between paragraphs', 'number')}${f('gap_scene_break', 'Scene breaks', 'number')}
        ${f('gap_chapter_start', 'Chapter start', 'number')}${f('gap_chapter_end', 'Chapter end', 'number')}</div>
      <div class="card stack"><div class="panel-title">Audio and server</div>
        ${f('chapter_bitrate', 'Chapter audio bitrate')}${f('export_bitrate', 'Export bitrate')}
        ${f('port', 'Port (restart to change)', 'number')}${sw('listen_on_network', 'Let the phone connect over Wi-Fi (restart to change)')}
        ${sw('open_browser', 'Open the browser when it starts')}</div>
      <div class="card stack"><div class="panel-title">Listening</div>
        <div class="big-url">${fmtLong(stats.listened)}</div><div class="muted">listened so far</div>
        <div class="big-url">${fmtLong(stats.generated)}</div><div class="muted">of audio made by Chatterbox</div></div>
    </div>
    <div class="row" style="margin-top:18px"><button class="btn gold" id="ssave">Save settings</button>
      <button class="btn" id="sunload">Put Chatterbox to sleep now</button></div>`;
  $('#ssave').onclick = async () => {
    const body = {};
    $$('[data-k]').forEach(i => body[i.dataset.k] = i.type === 'checkbox' ? i.checked : i.value);
    await attempt(() => post('/api/settings', body), 'Saved.');
    voicesCache = null;
    viewSettings();
  };
  $('#sunload').onclick = () => attempt(() => post('/api/engine/unload'), 'Chatterbox is asleep - the graphics card is free.');
}

// ------------------------------------------------------------------------------------------------ polling
let lastBusy = false;
async function poll() {
  try {
    const st = await get('/api/jobs');
    const active = st.jobs.filter(j => ['queued', 'running'].includes(j.status)).length;
    const badge = $('#queueBadge');
    badge.textContent = active; badge.classList.toggle('hidden', !active);
    if (currentView === 'viewQueue') refreshQueue(st);
    if (lastBusy && !active && currentView === 'viewBook') route();
    lastBusy = !!active;
  } catch (e) {}
  setTimeout(poll, lastBusy ? 2000 : 5000);
}

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
route();
poll();
