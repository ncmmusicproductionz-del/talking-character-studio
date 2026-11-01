'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtTime = s => { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };

const EXAMPLE = `# Why is Santa red?
Everyone thinks Coca-Cola made Santa *red*. That's a myth! He was wearing red in drawings from the 1800s, long before the famous adverts.

# Is there sound in space?
Space is almost completely silent. Sound needs air to travel, and space has almost none. So why do movie explosions boom? [think]

# The real Halloween
Halloween began with the old Celtic festival of *Samhain*. People believed ghosts walked the earth that night. [idea] Spooky, right? Follow for more.`;

const TAGS = [
  ['Sets', null],
  ['[set: studio]', 'Night studio'], ['[set: christmas]', 'Cosy Christmas'], ['[set: halloween]', 'Spooky night'],
  ['[set: history]', 'Old library'], ['[set: space]', 'Space deck'], ['[set: tech]', 'Neon lab'],
  ['[set: nature]', 'Forest cabin'], ['[set: ocean]', 'Ocean room'], ['[set: mystery]', 'Detective office'],
  ['Gestures', null],
  ['[point]', 'Points'], ['[point up]', 'Points up'], ['[explain]', 'Explains'], ['[open]', 'Open arms'], ['[think]', 'Hand on chin'],
  ['[wave]', 'Waves'], ['[thumbs]', 'Thumbs up'], ['[celebrate]', 'Arms up'], ['[present]', 'Presents'], ['[shrug]', 'Shrugs'],
  ['[facepalm]', 'Facepalm'], ['[clap]', 'Claps'], ['[count]', 'Counts'], ['[stop]', 'Palm out'], ['[fist]', 'Fist pump'],
  ['[type]', 'Types on the laptop'], ['[dance]', 'Dances'], ['[rest]', 'Rests'],
  ['Faces', null],
  ['[happy]', 'Happy'], ['[excited]', 'Excited'], ['[surprised]', 'Surprised'], ['[shocked]', 'Shocked + sweat'], ['[amazed]', 'Star eyes'],
  ['[love]', 'Heart eyes'], ['[laugh]', 'Laughing'], ['[wink]', 'Wink'], ['[cool]', 'Sunglasses'], ['[confused]', 'Confused ?'],
  ['[suspicious]', 'Side-eye'], ['[focused]', 'Focused'], ['[determined]', 'Determined'],
  ['[angry]', 'Angry'], ['[mad]', 'Furious'], ['[sad]', 'Sad'], ['[cry]', 'Crying'], ['[tired]', 'Tired'], ['[sleepy]', 'Asleep zzz'],
  ['[dizzy]', 'Dizzy spirals'],
  ['Moves', null],
  ['[nod]', 'Nods yes'], ['[shake]', 'Shakes head no'], ['[bounce]', 'Bounces'], ['[jump]', 'Jumps'],
  ['[look around]', 'Looks around'], ['[lean]', 'Leans in'], ['[tilt]', 'Tilts head'],
  ['Extras', null],
  ['[idea]', 'Lightbulb pops up'], ['[image: roman forum]', 'Picture to search for'], ['[noimage]', 'No picture or clip here'],
  ['[clip: rocket launch]', 'Video clip to search for'], ['[broll: city at night]', 'Full-screen video clip'],
  ['[note: Not Coca-Cola!]', 'Fact card on screen'],
  ['# Chapter title', 'New chapter and new set'], ['*word*', 'Highlight a word'],
];

const state = Object.assign({
  voiceMode: 'edge', voice: 'en-US-AndrewNeural', winVoice: '', speed: 0, captionStyle: 'bold', camera: true,
  setMode: 'auto', stageMode: 'mix', overlays: true, overrides: {}, format: 'vertical', quality: 'final', fps: 24,
  charMode: 'classic', charSeed: 0, charCustom: { outfit: 'hoodie', hat: 'cap', color: 'charcoal', accent: 'blue' },
  ftg: false, ftgSources: null, ftgDisplay: 'screen', ftgScope: 'all', charImage: null,
  pics: false, picSources: null, picLicense: 'standard', picMode: 'auto', music: null, musicVol: 22, recording: null,
}, (() => { try { return JSON.parse(localStorage.getItem('tcs-state') || '{}'); } catch (e) { return {}; } })());
let voices = null, themes = [], planTimer = null, planSeq = 0, lastSceneCount = -1, audioEl = null;
let picChosen = {}, picQueries = {}, picRowsLoaded = false, currentJob = null;

function save() { try { localStorage.setItem('tcs-state', JSON.stringify(state)); localStorage.setItem('tcs-script', $('script').value); } catch (e) {} }
function toast(msg) { const t = $('toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2600); }
function setErr(msg) { $('actionerr').textContent = msg || ''; }
function friendly(e) { return /failed to fetch|networkerror|load failed/i.test(e.message || '') ? "Can't reach the studio. Is its black window still open?" : (e.message || String(e)); }
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: 'POST', body: typeof body === 'string' || body instanceof Blob ? body : JSON.stringify(body) });
  const j = await r.json();
  if (j && j.error) throw new Error(j.error);
  return j;
}

/* ------------------------------------------------------------------ navigation */
document.querySelectorAll('.navbtn').forEach(b => b.onclick = () => showView(b.dataset.view));
function showView(v) {
  document.querySelectorAll('.navbtn').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  document.querySelectorAll('.view').forEach(s => s.classList.toggle('active', s.id === 'view-' + v));
  if (v === 'library') loadLibrary();
}
document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => closeModal(b.dataset.close));
function openModal(id) { $(id).classList.add('open'); }
function closeModal(id) {
  $(id).classList.remove('open');
  $(id).querySelectorAll('video').forEach(v => v.pause());
}
document.querySelectorAll('.modal').forEach(m => m.addEventListener('click', e => { if (e.target === m && m.id !== 'm-render') closeModal(m.id); }));

/* ------------------------------------------------------------------ script */
const scriptEl = $('script');
scriptEl.value = localStorage.getItem('tcs-script') || '';
scriptEl.addEventListener('input', () => { updateStats(); save(); picRowsLoaded = false; schedulePlan(); });
function updateStats() {
  const text = scriptEl.value;
  const words = text.split(/\s+/).filter(w => w && !w.startsWith('[') && !w.startsWith('#') && !/^[*\-]+$/.test(w)).length;
  $('st-words').textContent = words + ' words';
  $('st-len').textContent = '~' + fmtTime(words / 2.5 * (1 - state.speed / 100));
}
$('btn-example').onclick = () => { scriptEl.value = EXAMPLE; state.overrides = {}; scriptEl.dispatchEvent(new Event('input')); };
$('btn-clear').onclick = () => { if (!scriptEl.value || confirm('Clear the script?')) { scriptEl.value = ''; state.overrides = {}; scriptEl.dispatchEvent(new Event('input')); } };
$('scriptfile').onchange = async e => { const f = e.target.files[0]; if (f) { scriptEl.value = await f.text(); state.overrides = {}; scriptEl.dispatchEvent(new Event('input')); } e.target.value = ''; };
const tagmenu = $('tagmenu');
tagmenu.innerHTML = TAGS.map(([t, d]) => d === null ? `<div class="mh">${esc(t)}</div>` : `<button data-t="${esc(t)}">${esc(t)}<span>${esc(d)}</span></button>`).join('');
$('btn-tags').onclick = e => { e.stopPropagation(); $('tplmenu').classList.remove('open'); $('genmenu').classList.remove('open'); tagmenu.classList.toggle('open'); };
document.addEventListener('click', () => tagmenu.classList.remove('open'));
tagmenu.querySelectorAll('button').forEach(b => b.onclick = () => {
  let t = b.dataset.t;
  const s = scriptEl.selectionStart, e = scriptEl.selectionEnd, v = scriptEl.value;
  if (t === '*word*') t = '*' + (v.slice(s, e) || 'word') + '*';
  if (t.startsWith('#')) t = (s > 0 && v[s - 1] !== '\n' ? '\n' : '') + '# Chapter title\n';
  else t = (s > 0 && !/\s/.test(v[s - 1]) ? ' ' : '') + t + ' ';
  scriptEl.setRangeText(t, s, e, 'end'); scriptEl.focus(); scriptEl.dispatchEvent(new Event('input'));
});
$('taghelp').innerHTML = TAGS.filter(t => t[1] !== null).map(([t, d]) => `<div><code>${esc(t)}</code><span>${esc(d)}</span></div>`).join('');

/* ------------------------------------------------------------------ templates */
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) { const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); }
}
const tplmenu = $('tplmenu');
tplmenu.innerHTML = '<div class="mh">Script templates</div>' + TEMPLATES.map(t => `
  <div class="tplrow"><div class="tx"><b>${esc(t.name)}</b><small>${esc(t.info)}</small></div>
    <button class="use" data-use="${t.id}">Use</button><button data-copy="${t.id}">Copy</button></div>`).join('') +
  `<div class="mh">Write scripts with an AI chatbot</div>
  <div class="tplrow"><div class="tx"><b>AI writing prompt</b><small>Paste into ChatGPT, Claude or Gemini and it writes in this format</small></div>
    <button data-copy="ai">Copy</button></div>`;
$('btn-templates').onclick = e => { e.stopPropagation(); tagmenu.classList.remove('open'); tplmenu.classList.toggle('open'); };
tplmenu.onclick = e => e.stopPropagation();
document.addEventListener('click', () => tplmenu.classList.remove('open'));
tplmenu.querySelectorAll('[data-copy]').forEach(b => b.onclick = async () => {
  const t = b.dataset.copy === 'ai' ? AI_PROMPT : TEMPLATES.find(x => x.id === b.dataset.copy).text;
  await copyText(t); tplmenu.classList.remove('open');
  toast(b.dataset.copy === 'ai' ? 'AI prompt copied. Paste it into your chatbot and fill in the topic.' : 'Template copied to the clipboard.');
});
tplmenu.querySelectorAll('[data-use]').forEach(b => b.onclick = () => {
  if (scriptEl.value.trim() && !confirm('Replace your current script with this template?')) return;
  scriptEl.value = TEMPLATES.find(x => x.id === b.dataset.use).text; state.overrides = {};
  tplmenu.classList.remove('open'); scriptEl.dispatchEvent(new Event('input'));
  const k = scriptEl.value.indexOf('{');
  if (k >= 0) { scriptEl.focus(); scriptEl.setSelectionRange(k, scriptEl.value.indexOf('}', k) + 1); }
  toast('Replace each {part in curly brackets} with your own words.');
});

/* ------------------------------------------------------------------ scene planner */
function schedulePlan(now) { clearTimeout(planTimer); planTimer = setTimeout(plan, now ? 10 : 1100); }
async function plan() {
  const box = $('scenes');
  const text = scriptEl.value;
  box.classList.toggle('vertical', state.format === 'vertical');
  if (!text.trim()) { box.innerHTML = '<div class="empty">Your scenes appear here as you write.</div>'; $('st-sets').textContent = '0 sets'; return; }
  const seq = ++planSeq;
  box.classList.add('loading');
  try {
    const j = await api('/api/plan', { script: text, format: state.format, set_mode: state.setMode, stage_mode: state.stageMode, overrides: state.overrides, character: charReq() });
    if (seq !== planSeq) return;
    if (lastSceneCount !== -1 && j.scenes.length !== lastSceneCount && Object.keys(state.overrides).length) {
      state.overrides = {}; save(); lastSceneCount = j.scenes.length; return plan();
    }
    lastSceneCount = j.scenes.length;
    $('st-sets').textContent = j.scenes.length + (j.scenes.length === 1 ? ' set' : ' sets');
    box.innerHTML = j.scenes.map(sc => `
      <div class="scene" data-i="${sc.index}">
        <div class="thumb"><img src="/plan/${esc(sc.thumb)}" alt="" loading="lazy">
          <span class="badge">Scene ${sc.index + 1} · ~${fmtTime(sc.seconds)}</span><span class="stage">${sc.stage === 'open' ? 'Open world' : 'Room'}</span>
          <button class="roll" title="New variation of this set">⟳</button></div>
        <div class="meta"><b>${esc(sc.title)}</b><p>${esc(sc.snippet)}</p><div class="look">${esc(sc.outfit)} · ${esc(sc.hat)}</div>
          <div class="sel2"><select class="th-sel">${themes.map(t => `<option value="${t.id}" ${t.id === sc.theme ? 'selected' : ''}>${esc(t.label)}</option>`).join('')}</select>
          <select class="st-sel"><option value="room" ${sc.stage !== 'open' ? 'selected' : ''}>Room</option><option value="open" ${sc.stage === 'open' ? 'selected' : ''}>Open</option></select></div></div>
      </div>`).join('') || '<div class="empty">No scenes yet.</div>';
    box.querySelectorAll('.scene').forEach((el, k) => {
      const sc = j.scenes[k];
      el.querySelector('.roll').onclick = () => { state.overrides[sc.index] = { theme: sc.theme, seed: Math.floor(Math.random() * 1e9) }; save(); schedulePlan(true); };
      el.querySelector('.th-sel').onchange = e => { state.overrides[sc.index] = Object.assign({}, state.overrides[sc.index] || {}, { theme: e.target.value }); save(); schedulePlan(true); };
      el.querySelector('.st-sel').onchange = e => { state.overrides[sc.index] = Object.assign({}, state.overrides[sc.index] || {}, { stage: e.target.value }); save(); schedulePlan(true); };
    });
  } catch (e) { if (seq === planSeq) box.innerHTML = `<div class="empty">${esc(friendly(e))}</div>`; }
  finally { if (seq === planSeq) box.classList.remove('loading'); }
}
$('btn-replan').onclick = () => schedulePlan(true);
$('setmode').onchange = e => { state.setMode = e.target.value; state.overrides = {}; save(); schedulePlan(true); };
$('stagemode').value = state.stageMode;
$('stagemode').onchange = e => { state.stageMode = e.target.value; Object.values(state.overrides).forEach(o => delete o.stage); save(); schedulePlan(true); };

/* ------------------------------------------------------------------ random script */
let genMinutes = 8;
const genmenu = $('genmenu');
$('btn-random').onclick = e => { e.stopPropagation(); tagmenu.classList.remove('open'); $('tplmenu').classList.remove('open'); genmenu.classList.toggle('open'); };
genmenu.onclick = e => e.stopPropagation();
document.addEventListener('click', () => genmenu.classList.remove('open'));
genmenu.querySelectorAll('#genlens button').forEach(b => b.onclick = () => {
  genMinutes = +b.dataset.m; genmenu.querySelectorAll('#genlens button').forEach(x => x.classList.toggle('on', x === b));
});
$('btn-generate-script').onclick = async () => {
  if (scriptEl.value.trim() && !confirm('Replace your current script with a new random one?')) return;
  const b = $('btn-generate-script'); b.disabled = true; b.textContent = 'Writing…';
  try {
    const j = await api(`/api/random_script?minutes=${genMinutes}&footage=${$('genclips').checked ? 1 : 0}`);
    scriptEl.value = j.script; state.overrides = {}; scriptEl.dispatchEvent(new Event('input'));
    genmenu.classList.remove('open');
    toast(`"${j.title}" · ${j.stories} stories · about ${j.minutes} min`);
  } catch (e) { toast(friendly(e)); }
  finally { b.disabled = false; b.textContent = 'Generate script'; }
};

/* ------------------------------------------------------------------ character */
const CHAR_HINTS = {
  classic: 'Your character sheet: grey hoodie, black cap, blue glow.',
  theme: 'Dressed for each set: Santa hat at Christmas, space suit in space, fedora in the detective office and more.',
  random: 'A new outfit, hat and colours for every scene. Press New look for a different mix.',
  custom: 'Pick the outfit, hat and colours yourself.',
  image: 'Use your own character: upload a picture (plus optional talking and blinking pictures) and the studio animates it.',
};
let myChars = [];
let charOpts = null, charTimer = null;
function charReq() { return { mode: state.charMode, seed: state.charSeed, custom: state.charCustom, image_id: state.charImage }; }
function charPreviewTheme() {
  const sel = document.querySelector('#scenes .scene select');
  return sel ? sel.value : 'studio';
}
function updateChar(replan) {
  document.querySelectorAll('#charmode button').forEach(b => b.classList.toggle('on', b.dataset.m === state.charMode));
  $('charhint').textContent = CHAR_HINTS[state.charMode] || '';
  $('charcustom').classList.toggle('hidden', state.charMode !== 'custom');
  $('charimage').classList.toggle('hidden', state.charMode !== 'image');
  $('btn-newlook').classList.toggle('hidden', !['theme', 'random'].includes(state.charMode));
  document.querySelectorAll('.mychar').forEach(el => el.classList.toggle('on', el.dataset.id === state.charImage));
  const c = state.charCustom;
  if (charOpts) {
    $('c-outfit').value = c.outfit; $('c-hat').value = c.hat;
    document.querySelectorAll('#c-color button').forEach(b => b.classList.toggle('on', b.dataset.id === c.color));
    document.querySelectorAll('#c-accent button').forEach(b => b.classList.toggle('on', b.dataset.id === c.accent));
    const mc = myChars.find(m => m.id === state.charImage);
    const lab = { classic: 'Classic look', theme: 'Changes with each set', random: 'New look each scene', image: mc ? mc.name : 'Add a character below' };
    $('charlabel').textContent = lab[state.charMode] ||
      ((charOpts.outfits.find(o => o.id === c.outfit) || {}).label + ' · ' + (charOpts.hats.find(o => o.id === c.hat) || {}).label);
  }
  const q = new URLSearchParams({ mode: state.charMode, seed: state.charSeed, outfit: c.outfit, hat: c.hat, color: c.color, accent: c.accent,
    theme: charPreviewTheme(), image_id: state.charImage || '' });
  const img = $('charimg');
  const src = '/api/character.png?' + q;
  if (img.getAttribute('src') !== src) { img.classList.add('busy'); img.onload = () => img.classList.remove('busy'); img.src = src; }
  save();
  if (replan) { clearTimeout(charTimer); charTimer = setTimeout(() => schedulePlan(true), 250); }
}
document.querySelectorAll('#charmode button').forEach(b => b.onclick = () => { state.charMode = b.dataset.m; updateChar(true); });
$('btn-newlook').onclick = () => { state.charSeed = Math.floor(Math.random() * 99999); updateChar(true); };
async function loadCharOptions() {
  try {
    charOpts = await api('/api/character_options');
    $('c-outfit').innerHTML = charOpts.outfits.map(o => `<option value="${o.id}">${esc(o.label)}</option>`).join('');
    $('c-hat').innerHTML = charOpts.hats.map(o => `<option value="${o.id}">${esc(o.label)}</option>`).join('');
    $('c-color').innerHTML = charOpts.colors.map(o => `<button data-id="${o.id}" title="${o.id}" style="background:${o.hex}"></button>`).join('');
    $('c-accent').innerHTML = charOpts.accents.map(o => `<button data-id="${o.id}" title="${o.id}" style="background:${o.hex};box-shadow:0 0 10px ${o.hex}"></button>`).join('');
    $('c-outfit').onchange = e => { state.charCustom.outfit = e.target.value; updateChar(true); };
    $('c-hat').onchange = e => { state.charCustom.hat = e.target.value; updateChar(true); };
    document.querySelectorAll('#c-color button').forEach(b => b.onclick = () => { state.charCustom.color = b.dataset.id; updateChar(true); });
    document.querySelectorAll('#c-accent button').forEach(b => b.onclick = () => { state.charCustom.accent = b.dataset.id; updateChar(true); });
  } catch (e) {}
  await loadMyChars();
  updateChar(false);
}
async function loadMyChars() {
  try { myChars = await api('/api/characters'); } catch (e) { myChars = []; }
  if (state.charImage && !myChars.some(m => m.id === state.charImage)) state.charImage = null;
  if (!state.charImage && myChars.length) state.charImage = myChars[0].id;
  $('mychars').innerHTML = myChars.map(m => `<div class="mychar" data-id="${m.id}" title="${esc(m.name)}">
      <img src="/api/character.png?mode=image&image_id=${m.id}" alt=""><span>${esc(m.name)}</span>
      <button data-del="${m.id}" title="Delete">✕</button></div>`).join('') || '<p class="tiny">No characters yet. Add one below.</p>';
  $('newchar').open = !myChars.length;
  $('mychars').querySelectorAll('.mychar').forEach(el => el.onclick = e => {
    if (e.target.dataset.del) return;
    state.charImage = el.dataset.id; updateChar(true);
  });
  $('mychars').querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
    const m = myChars.find(x => x.id === b.dataset.del);
    if (!confirm('Delete ' + (m ? m.name : 'this character') + '?')) return;
    await api('/api/character_delete', { id: b.dataset.del });
    if (state.charImage === b.dataset.del) state.charImage = null;
    await loadMyChars(); updateChar(true);
  });
}
const ncFiles = {};
document.querySelectorAll('.ncslot input').forEach(inp => inp.onchange = () => {
  const f = inp.files[0]; if (!f) return;
  const r = new FileReader();
  r.onload = () => { ncFiles[inp.dataset.slot] = r.result; inp.parentElement.querySelector('img').src = r.result; };
  r.readAsDataURL(f);
});
$('nc-save').onclick = async () => {
  if (!ncFiles.idle) { $('nc-msg').textContent = 'Add the main picture first.'; return; }
  $('nc-save').disabled = true; $('nc-msg').textContent = 'Saving… (removing the background)';
  try {
    const j = await api('/api/character_upload', Object.assign({ name: $('nc-name').value || 'My character' }, ncFiles));
    state.charImage = j.id; state.charMode = 'image';
    Object.keys(ncFiles).forEach(k => delete ncFiles[k]);
    document.querySelectorAll('.ncslot img').forEach(i => i.removeAttribute('src')); $('nc-name').value = '';
    $('nc-msg').textContent = ''; await loadMyChars(); updateChar(true); toast('Character saved.');
  } catch (e) { $('nc-msg').textContent = friendly(e); }
  finally { $('nc-save').disabled = false; }
};
loadCharOptions();

/* ------------------------------------------------------------------ voices */
function segInit(id, key, attr, after) {
  const el = $(id);
  el.querySelectorAll('button').forEach(b => {
    b.classList.toggle('on', String(state[key]) === b.dataset[attr]);
    b.onclick = () => {
      state[key] = isNaN(+b.dataset[attr]) ? b.dataset[attr] : +b.dataset[attr];
      el.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); save(); if (after) after();
    };
  });
}
function refreshVoiceMode() {
  ['edge', 'windows', 'file'].forEach(m => $('vm-' + m).classList.toggle('hidden', state.voiceMode !== m));
  $('speedbox').classList.toggle('hidden', state.voiceMode === 'file');
}
segInit('voicemode', 'voiceMode', 'v', refreshVoiceMode);
function renderEdgeVoices() {
  const list = $('edgelist');
  if (!voices) return;
  list.innerHTML = voices.edge.map(v => {
    const [name, rest] = v.name.split(' (');
    return `<div class="voice ${v.id === state.voice ? 'on' : ''}" data-id="${v.id}"><button class="play" title="Hear it">▶</button>
      <div><b>${esc(name)}</b><small>${esc((rest || '').replace(')', ''))}</small></div></div>`;
  }).join('');
  list.querySelectorAll('.voice').forEach(el => {
    el.onclick = () => { state.voice = el.dataset.id; save(); list.querySelectorAll('.voice').forEach(x => x.classList.toggle('on', x === el)); };
    el.querySelector('.play').onclick = ev => { ev.stopPropagation(); playPreview('edge', el.dataset.id, ev.currentTarget); };
  });
  if (!voices.edge_available) $('edgelist').insertAdjacentHTML('afterbegin', '<p class="err">The AI voice library is missing. Run Setup again or use Windows voices.</p>');
}
function playPreview(mode, id, btn) {
  if (audioEl) { audioEl.pause(); document.querySelectorAll('.play').forEach(p => { p.textContent = '▶'; p.classList.remove('busy'); }); }
  if (audioEl && audioEl._id === mode + id) { audioEl = null; return; }
  btn.classList.add('busy');
  audioEl = new Audio(`/api/voice_preview?mode=${mode}&voice=${encodeURIComponent(id)}`);
  audioEl._id = mode + id;
  audioEl.oncanplay = () => { btn.classList.remove('busy'); btn.textContent = '■'; };
  audioEl.onended = () => { btn.textContent = '▶'; audioEl = null; };
  audioEl.onerror = () => { btn.classList.remove('busy'); btn.textContent = '▶'; toast('Could not play that voice. Check your internet connection.'); };
  audioEl.play().catch(() => {});
}
$('winvoice').onchange = e => { state.winVoice = e.target.value; save(); };
$('btn-winpreview').onclick = e => playPreview('windows', state.winVoice || $('winvoice').value, e.currentTarget);
$('speed').value = state.speed;
const speedLabel = () => { $('speedval').textContent = state.speed == 0 ? 'Normal' : (state.speed > 0 ? '+' : '') + state.speed + '%'; };
$('speed').oninput = e => { state.speed = +e.target.value; speedLabel(); updateStats(); save(); };
speedLabel();
$('recfile').onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  $('recname').textContent = 'Uploading ' + f.name + '...';
  try { const j = await api('/api/upload?name=' + encodeURIComponent(f.name), f); state.recording = { id: j.id, name: f.name }; save(); refreshRecording(); }
  catch (err) { $('recname').textContent = friendly(err); }
  e.target.value = '';
};
function refreshRecording() {
  const r = state.recording;
  $('recname').textContent = r ? '✓ ' + r.name : 'Choose your recording (mp3, wav, m4a)';
  $('recname').parentElement.classList.toggle('has', !!r);
}

/* ------------------------------------------------------------------ look, pictures, music, output */
document.querySelectorAll('#captiles button').forEach(b => {
  b.classList.toggle('on', b.dataset.c === state.captionStyle);
  b.onclick = () => { state.captionStyle = b.dataset.c; document.querySelectorAll('#captiles button').forEach(x => x.classList.toggle('on', x === b)); save(); };
});
$('camera').checked = !!state.camera;
$('camera').onchange = e => { state.camera = e.target.checked; save(); };
$('overlays').checked = state.overlays !== false;
$('overlays').onchange = e => { state.overlays = e.target.checked; save(); };
$('pics').checked = !!state.pics;
const refreshPics = () => { $('picopts').classList.toggle('hidden', !state.pics); $('btn-review').classList.toggle('hidden', state.picMode !== 'chosen'); };
$('pics').onchange = e => { state.pics = e.target.checked; save(); refreshPics(); };
$('piclicense').value = state.picLicense;
$('piclicense').onchange = e => { state.picLicense = e.target.value; picRowsLoaded = false; save(); };
segInit('picmode', 'picMode', 'p', refreshPics);
async function loadSources() {
  const list = await api('/api/image_sources');
  if (!state.picSources) state.picSources = list.filter(s => !s.needs_key && s.id !== 'openverse').map(s => s.id);
  $('srcchips').innerHTML = list.map(s => {
    const usable = !s.needs_key || s.key_set;
    return `<span class="chip ${usable ? (state.picSources.includes(s.id) ? 'on' : '') : 'off'}" data-id="${s.id}" title="${esc(s.desc)}">${esc(s.name)}${usable ? '' : ' (key)'}</span>`;
  }).join('');
  $('srcchips').querySelectorAll('.chip').forEach(c => c.onclick = () => {
    if (c.classList.contains('off')) { showView('settings'); return; }
    const id = c.dataset.id;
    state.picSources = state.picSources.includes(id) ? state.picSources.filter(x => x !== id) : state.picSources.concat([id]);
    c.classList.toggle('on'); picRowsLoaded = false; save();
  });
}
$('musicfile').onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  $('musicname').textContent = 'Uploading ' + f.name + '...';
  try { const j = await api('/api/upload?name=' + encodeURIComponent(f.name), f); state.music = { id: j.id, name: f.name }; save(); refreshMusic(); }
  catch (err) { $('musicname').textContent = friendly(err); }
  e.target.value = '';
};
$('btn-musicremove').onclick = () => { state.music = null; save(); refreshMusic(); };
$('musicvol').value = state.musicVol;
$('musicvol').oninput = e => { state.musicVol = +e.target.value; $('musicvolval').textContent = state.musicVol + '%'; save(); };
function refreshMusic() {
  $('musicname').textContent = state.music ? '♪ ' + state.music.name : 'Add background music (optional)';
  $('musicname').parentElement.classList.toggle('has', !!state.music);
  $('musicopts').classList.toggle('hidden', !state.music);
  $('musicvolval').textContent = state.musicVol + '%';
}
document.querySelectorAll('#fmt button').forEach(b => {
  b.classList.toggle('on', b.dataset.f === state.format);
  b.onclick = () => { state.format = b.dataset.f; document.querySelectorAll('#fmt button').forEach(x => x.classList.toggle('on', x === b)); save(); schedulePlan(true); };
});
segInit('quality', 'quality', 'q');
segInit('fps', 'fps', 'r');


/* ------------------------------------------------------------------ footage */
if (state.ftgDisplay === 'full') state.ftgDisplay = 'inside';
$('ftg').checked = !!state.ftg;
const refreshFtg = () => $('ftgopts').classList.toggle('hidden', !state.ftg);
$('ftg').onchange = e => { state.ftg = e.target.checked; save(); refreshFtg(); if (state.ftg) loadFootage(); };
segInit('ftgdisplay', 'ftgDisplay', 'd');
segInit('ftgscope', 'ftgScope', 's');
async function loadFootage() {
  try {
    const list = await api('/api/footage_sources');
    if (!state.ftgSources) state.ftgSources = list.map(s => s.id);
    $('ftgchips').innerHTML = list.map(s => {
      const usable = !s.key || s.ready;
      return `<span class="chip ${usable ? (state.ftgSources.includes(s.id) ? 'on' : '') : 'off'}" data-id="${s.id}" title="${esc(s.desc)}">${esc(s.name)}${usable ? '' : ' (key)'}</span>`;
    }).join('');
    $('ftgchips').querySelectorAll('.chip').forEach(c => c.onclick = () => {
      if (c.classList.contains('off')) { showView('settings'); return; }
      const id = c.dataset.id;
      state.ftgSources = state.ftgSources.includes(id) ? state.ftgSources.filter(x => x !== id) : state.ftgSources.concat([id]);
      c.classList.toggle('on'); save();
    });
    const mine = await api('/api/myclips');
    $('myclips').innerHTML = mine.map(c => `<div><span title="${esc(c.name)}">🎬 ${esc(c.name)}</span><small>${(c.size / 1048576).toFixed(1)} MB</small>
      <button data-n="${esc(c.name)}" title="Remove">✕</button></div>`).join('');
    $('myclips').querySelectorAll('button').forEach(b => b.onclick = async () => {
      if (!confirm('Remove ' + b.dataset.n + ' from your clips?')) return;
      await api('/api/delete_clip', { name: b.dataset.n }); loadFootage();
    });
  } catch (e) { $('ftgchips').innerHTML = `<span class="tiny">${esc(friendly(e))}</span>`; }
}
$('clipfile').onchange = async e => {
  const files = [...e.target.files]; e.target.value = '';
  for (const [i, f] of files.entries()) {
    $('clipdrop').textContent = `Uploading ${f.name} (${i + 1}/${files.length})…`;
    try { await api('/api/upload_clip?name=' + encodeURIComponent(f.name), f); }
    catch (err) { toast(f.name + ': ' + friendly(err)); }
  }
  $('clipdrop').textContent = '＋ Upload your own clips';
  loadFootage();
};
refreshFtg();
if (state.ftg) loadFootage();

/* ------------------------------------------------------------------ picture review */
$('btn-review').onclick = async () => {
  openModal('m-pictures');
  if (picRowsLoaded) return;
  if (!scriptEl.value.trim()) { $('picstatus').textContent = 'Write a script first.'; return; }
  $('picstatus').textContent = 'Searching the picture libraries (up to a minute)...'; $('picrows').innerHTML = '';
  try {
    const j = await api('/api/plan_images', { script: scriptEl.value, sources: state.picSources, license: state.picLicense, format: state.format });
    picChosen = {}; picQueries = {};
    j.rows.forEach(row => { picChosen[row.index] = row.candidates.length ? row.candidates[0].id : null; drawPicRow(row); });
    picRowsLoaded = true;
    $('picstatus').textContent = j.rows.length + ' picture spots found.';
  } catch (e) { $('picstatus').textContent = friendly(e); }
};
function drawPicRow(row) {
  const el = document.createElement('div'); el.className = 'prow';
  el.innerHTML = `<div class="tiny">Part ${row.index + 1}: ${esc(row.text)}</div><div class="q"><input type="text" value="${esc(row.query)}">
    <button class="tbtn">Search</button><button class="tbtn">No picture</button></div><div class="thumbs"></div>`;
  $('picrows').appendChild(el);
  const [search, none] = el.querySelectorAll('.q button');
  search.onclick = async () => {
    const q = el.querySelector('input').value; picQueries[row.index] = q;
    try { const j = await api('/api/search_images', { query: q, sources: state.picSources, license: state.picLicense, format: state.format });
      picChosen[row.index] = j.candidates.length ? j.candidates[0].id : null; fill(j.candidates); } catch (e) { toast(friendly(e)); }
  };
  none.onclick = () => { picChosen[row.index] = null; mark(); };
  const box = el.querySelector('.thumbs');
  function mark() { box.querySelectorAll('.th').forEach(d => d.classList.toggle('sel', d.dataset.id === picChosen[row.index])); }
  function fill(c) {
    box.innerHTML = c.length ? '' : '<span class="tiny">Nothing found. Try other words.</span>';
    c.forEach(x => { const d = document.createElement('div'); d.className = 'th'; d.dataset.id = x.id; d.title = x.title + ' (' + x.license + ')';
      d.innerHTML = `<img src="${esc(x.thumb)}" referrerpolicy="no-referrer" loading="lazy"><span>${esc(x.license)}${x.attribution_required ? ' · credit' : ''}</span>`;
      d.onclick = () => { picChosen[row.index] = x.id; mark(); }; box.appendChild(d); });
    mark();
  }
  fill(row.candidates);
}

/* ------------------------------------------------------------------ generate */
function buildRequest(seconds) {
  const req = { script: scriptEl.value, mode: state.voiceMode, voice: state.voiceMode === 'windows' ? (state.winVoice || $('winvoice').value) : state.voice,
    speed: state.speed, format: state.format, quality: state.quality, fps: state.fps, seconds: seconds || null,
    look: { set_mode: state.setMode, stage: state.stageMode, overlays: state.overlays, camera: state.camera ? 'dynamic' : 'static', caption_style: state.captionStyle, overrides: state.overrides, character: charReq() } };
  if (state.voiceMode === 'file') req.audio_id = state.recording ? state.recording.id : '';
  if (state.music) req.music = { id: state.music.id, volume: state.musicVol / 100 };
  if (state.ftg) req.footage = { on: true, sources: state.ftgSources, display: state.ftgDisplay, scope: state.ftgScope };
  if (state.pics) {
    req.images = { mode: 'auto', sources: state.picSources, license: state.picLicense };
    if (state.picMode === 'chosen' && picRowsLoaded) { req.images.mode = 'chosen'; req.images.chosen = picChosen; req.images.queries = picQueries; }
  }
  return req;
}
async function generate(seconds) {
  setErr('');
  if (!scriptEl.value.trim()) { setErr('Write or paste a script first.'); scriptEl.focus(); return; }
  if (state.voiceMode === 'file' && !state.recording) { setErr('Choose your recording first.'); return; }
  $('btn-make').disabled = $('btn-preview').disabled = true;
  try {
    const j = await api('/api/generate', buildRequest(seconds));
    currentJob = j.id; openRender(seconds); poll(j.id);
  } catch (e) { setErr(friendly(e)); $('btn-make').disabled = $('btn-preview').disabled = false; }
}
function openRender(seconds) {
  $('r-title').textContent = seconds ? 'Making a 15 second preview' : 'Making your video';
  $('r-fill').style.width = '0%'; $('r-pct').textContent = '0%'; $('r-msg').textContent = 'Starting'; $('r-time').textContent = ''; $('r-eta').textContent = '';
  $('liveimg').classList.remove('show'); $('liveph').classList.remove('hidden');
  $('m-render').querySelector('.live').classList.toggle('vertical', state.format === 'vertical');
  openModal('m-render');
}
async function poll(id) {
  let lastLive = 0;
  while (true) {
    await new Promise(r => setTimeout(r, 1000));
    let s;
    try { s = await api('/api/status?id=' + id); } catch (e) { $('r-msg').textContent = friendly(e); continue; }
    const p = s.progress || 0;
    $('r-fill').style.width = Math.max(2, p * 100) + '%'; $('r-pct').textContent = Math.round(p * 100) + '%';
    $('r-msg').textContent = s.message || '';
    if (s.elapsed) {
      $('r-time').textContent = 'Elapsed ' + fmtTime(s.elapsed);
      $('r-eta').textContent = p > 0.2 && p < 0.99 ? 'About ' + fmtTime(s.elapsed / p * (1 - p)) + ' left' : '';
    }
    if (s.live && Date.now() - lastLive > 1800 && p > 0.15) {
      lastLive = Date.now();
      const img = $('liveimg'); const n = new Image();
      n.onload = () => { img.src = n.src; img.classList.add('show'); $('liveph').classList.add('hidden'); };
      n.src = s.live + '?t=' + Date.now();
    }
    if (s.status === 'done') { closeModal('m-render'); showResult(s); break; }
    if (s.status === 'error') { closeModal('m-render'); setErr(s.error || 'Something went wrong.'); break; }
    if (s.status === 'cancelled') { closeModal('m-render'); toast('Cancelled'); break; }
    if (s.status === 'unknown') { closeModal('m-render'); setErr('The job was lost. Try again.'); break; }
  }
  currentJob = null;
  $('btn-make').disabled = $('btn-preview').disabled = false;
  loadLibrary(true);
}
$('btn-cancel').onclick = () => { if (currentJob) api('/api/cancel', { id: currentJob }).catch(() => {}); $('r-msg').textContent = 'Stopping...'; };
function showResult(s) {
  $('res-sub').textContent = fmtTime(s.seconds) + ' long · ' + (s.sets || []).map(x => x.title).join(' → ');
  const v = $('res-video'); v.src = s.files.video + '?t=' + Date.now(); v.play().catch(() => {});
  $('dl-video').href = s.files.video + '?dl=1'; $('dl-srt').href = s.files.srt; $('dl-audio').href = s.files.audio;
  $('dl-credits').classList.toggle('hidden', !s.files.credits); if (s.files.credits) $('dl-credits').href = s.files.credits;
  $('res-warn').innerHTML = (s.warnings || []).map(w => '<li>' + esc(w) + '</li>').join('');
  openModal('m-result');
}
$('btn-make').onclick = () => generate(null);
$('btn-preview').onclick = () => generate(15);

/* ------------------------------------------------------------------ library */
async function loadLibrary(quiet) {
  let items;
  try { items = await api('/api/history'); } catch (e) { if (!quiet) $('libgrid').innerHTML = `<div class="libempty">${esc(friendly(e))}</div>`; return; }
  $('libcount').textContent = items.length || '';
  if (!items.length) {
    $('libgrid').innerHTML = `<div class="libempty"><img src="/api/avatar.png" alt=""><h2>No videos yet</h2><p>Videos you make show up here.</p></div>`;
    return;
  }
  $('libgrid').innerHTML = items.map(m => `
    <div class="vcard" data-id="${esc(m.id)}">
      <div class="pv" style="background-image:url('${m.files.poster ? esc(m.files.poster) : '/api/avatar.png'}')">
        <span class="fmtb">${m.format === 'landscape' ? '16:9' : '9:16'}${m.preview ? ' · PREVIEW' : ''}</span>
        <span class="tag">${fmtTime(m.seconds || 0)}</span></div>
      <div class="info"><b>${esc(m.title)}</b><small>${new Date(m.created * 1000).toLocaleString()}</small>
        <div class="acts"><a href="${esc(m.files.video)}?dl=1" download onclick="event.stopPropagation()">Download</a>
          <button class="del">Delete</button></div></div>
    </div>`).join('');
  $('libgrid').querySelectorAll('.vcard').forEach((el, k) => {
    const m = items[k];
    el.onclick = () => {
      $('pl-title').textContent = m.title;
      const v = $('pl-video'); v.src = m.files.video; v.play().catch(() => {});
      $('pl-dl').innerHTML = `<a class="btn primary small" href="${esc(m.files.video)}?dl=1" download>Download MP4</a>` +
        (m.files.srt ? `<a class="btn secondary small" href="${esc(m.files.srt)}" download>Captions .srt</a>` : '') +
        (m.files.credits ? `<a class="btn secondary small" href="${esc(m.files.credits)}" download>Picture credits</a>` : '');
      openModal('m-player');
    };
    el.querySelector('.del').onclick = async ev => {
      ev.stopPropagation();
      if (!confirm('Delete "' + m.title + '"? This removes the video and its files from the output folder.')) return;
      try { await api('/api/delete', { id: m.id }); toast('Deleted'); loadLibrary(true); } catch (e) { toast(friendly(e)); }
    };
  });
}
const openFolder = () => api('/api/open_folder', {}).catch(e => toast(friendly(e)));
$('btn-openfolder').onclick = openFolder; $('btn-openfolder2').onclick = openFolder;

/* ------------------------------------------------------------------ settings */
$('btn-savekeys').onclick = async () => {
  try {
    await api('/api/config', { pexels_key: $('k_pexels').value, pixabay_key: $('k_pixabay').value, unsplash_key: $('k_unsplash').value });
    ['k_pexels', 'k_pixabay', 'k_unsplash'].forEach(i => $(i).value = '');
    $('keymsg').textContent = 'Saved.'; loadSources();
  } catch (e) { $('keymsg').textContent = friendly(e); }
};

/* ------------------------------------------------------------------ connection + start */
async function ping() {
  try { await fetch('/api/themes', { cache: 'no-store' }); $('serverdot').className = 'dot ok'; $('serverstate').textContent = 'Studio running'; }
  catch (e) { $('serverdot').className = 'dot bad'; $('serverstate').textContent = 'Studio not running'; }
}
async function start() {
  refreshVoiceMode(); refreshRecording(); refreshMusic(); refreshPics(); updateStats();
  try {
    themes = await api('/api/themes');
    $('setmode').innerHTML = '<option value="auto">Auto (from the script)</option>' + themes.map(t => `<option value="${t.id}">${esc(t.label)}</option>`).join('');
    $('setmode').value = state.setMode;
    voices = await api('/api/voices');
    renderEdgeVoices();
    $('winvoice').innerHTML = voices.windows.map(v => `<option>${esc(v)}</option>`).join('') || '<option value="">No Windows voices found</option>';
    if (state.winVoice) $('winvoice').value = state.winVoice;
    loadSources().catch(() => {});
    loadLibrary(true);
    schedulePlan(true);
  } catch (e) { setErr(friendly(e)); }
  ping(); setInterval(ping, 5000);
}
start();
