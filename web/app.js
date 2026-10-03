'use strict';
const $ = (s, r = document) => r.querySelector(s);
const sleep = ms => new Promise(r => setTimeout(r, ms));
let token = null, ws = null, log = [], busy = false, speaking = false, listening = false;
let state = 'idle', level = 0, target = 0, tab = 'chat', talking = false, hasVoice = false;
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

/* ---------------- API ---------------- */
async function api(path, opt = {}) {
  const r = await fetch(path, { ...opt, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) } });
  if (!r.ok) { let d = ''; try { d = (await r.json()).detail; } catch (e) {} throw new Error(d || r.status); }
  return r.json();
}
const post = (p, b) => api(p, { method: 'POST', body: JSON.stringify(b || {}) });

/* ---------------- Config local (música, voz) ---------------- */
const store = {
  get: (k, d) => { try { const v = localStorage.getItem('kyky.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set: (k, v) => { try { localStorage.setItem('kyky.' + k, JSON.stringify(v)); } catch (e) {} },
};
function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open('kyky', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('files');
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
}
async function idbPut(k, v) { const d = await idb(); return new Promise(r => { const t = d.transaction('files', 'readwrite'); t.objectStore('files').put(v, k); t.oncomplete = r; }); }
async function idbGet(k) { const d = await idb(); return new Promise(r => { const q = d.transaction('files').objectStore('files').get(k); q.onsuccess = () => r(q.result); q.onerror = () => r(null); }); }
async function idbDel(k) { const d = await idb(); return new Promise(r => { const t = d.transaction('files', 'readwrite'); t.objectStore('files').delete(k); t.oncomplete = r; }); }

// devolve 'ok', 'sem-musica' ou 'bloqueado' (o navegador não deixou tocar sem um clique)
async function playTheme(loop) {
  const blob = await idbGet('theme'); if (!blob) return 'sem-musica';
  const a = $('#theme'); a.src = URL.createObjectURL(blob); a.loop = !!loop;
  const vol = store.get('vol', 0.7); a.volume = 0;
  try { await a.play(); } catch (e) { return 'bloqueado'; }
  let v = 0; const iv = setInterval(() => { v = Math.min(vol, v + vol / 20); a.volume = v; if (v >= vol) clearInterval(iv); }, 100);
  return 'ok';
}
function fadeOutTheme() {
  const a = $('#theme'); const o = setInterval(() => { a.volume = Math.max(0, a.volume - 0.04); if (a.volume <= 0.01) { clearInterval(o); a.pause(); } }, 120);
}

/* ---------------- Modo foco: palmas/estalos (sentinel.py) ligam e desligam; a música só toca aqui ---------------- */
let focus = false;
async function setFocus(on) {
  focus = on; $('#focus-chip').classList.toggle('hidden', !on);
  if (!on) { fadeOutTheme(); $('#subcaption').textContent = 'modo foco desligado'; return; }
  const r = await playTheme(true);
  if (r === 'sem-musica') $('#subcaption').textContent = 'modo foco ligado — escolha a música em Ajustes';
  else if (r === 'bloqueado') {
    $('#subcaption').textContent = 'modo foco ligado — clique em qualquer lugar para tocar a música';
    document.addEventListener('pointerdown', () => { if (focus) playTheme(true); }, { once: true });
  } else $('#subcaption').textContent = 'modo foco ligado';
}
$('#focus-chip').onclick = () => setFocus(false);

/* ---------------- Boot ---------------- */
async function boot() {
  const ul = $('#boot-steps'), bar = $('#boot-bar');
  const status = fetch('/api/status').then(r => r.json()).catch(() => null);
  const authState = fetch('/api/auth/state').then(r => r.json());
  const steps = [
    ['Núcleo da Kyky', async () => [true, 'online']],
    ['Cofre de chaves', async () => [true, 'selado']],
    ['Provedores de IA', async () => { const s = await status; return s ? [s.providers.length > 0, s.providers.length + '/' + s.total_providers] : [false, 'erro']; }],
    ['Busca na web', async () => { const s = await status; return [!!(s && s.search), s && s.search ? 'ativa' : 'sem chave']; }],
    ['Memória local', async () => [true, 'sincronizada']],
    ['Canvas da faculdade', async () => { const s = await status; return [!!(s && s.canvas.ok), s && s.canvas.ok ? 'conectado' : 'indisponível']; }],
    ['GitHub', async () => { const s = await status; return [!!(s && s.github.ok), s && s.github.ok ? s.github.detail : 'indisponível']; }],
    ['Reconhecimento de voz', async () => [!!window.MediaRecorder, window.MediaRecorder ? 'Whisper pronto' : 'não suportado']],
    ['Aguardando autenticação', async () => [true, '···']],
  ];
  for (let i = 0; i < steps.length; i++) {
    const li = document.createElement('li');
    li.innerHTML = `<span>${steps[i][0]}</span><span class="st run">···</span>`; ul.appendChild(li);
    const [ok, txt] = await steps[i][1]();
    await sleep(380);
    const st = li.querySelector('.st'); st.className = 'st ' + (ok ? 'ok' : 'fail'); st.textContent = (ok ? '✔ ' : '✖ ') + txt;
    bar.style.width = ((i + 1) / steps.length * 100) + '%';
  }
  const as = await authState; hasVoice = !!as.has_voice;
  $('#login').classList.remove('hidden');
  if (!as.has_password) {
    $('#login-title').textContent = 'PRIMEIRO ACESSO — CRIE SUA SENHA';
    $('#pw2').classList.remove('hidden'); $('#btn-login').textContent = 'CRIAR SENHA';
  } else if (as.has_voice) $('#btn-voice').classList.remove('hidden');
  $('#pw').focus();
  $('#btn-login').onclick = async () => {
    const pw = $('#pw').value, msg = $('#login-msg'); msg.textContent = '';
    try {
      if (!as.has_password) {
        if (pw !== $('#pw2').value) { msg.textContent = 'As senhas não coincidem.'; return; }
        token = (await post('/api/auth/setup', { password: pw })).token;
      } else token = (await post('/api/auth/login', { password: pw })).token;
      enter();
    } catch (e) { msg.textContent = 'Acesso negado: ' + e.message; }
  };
  $('#pw').addEventListener('keydown', e => { if (e.key === 'Enter') $('#btn-login').click(); });
  $('#pw2').addEventListener('keydown', e => { if (e.key === 'Enter') $('#btn-login').click(); });
  $('#btn-voice').onclick = () => voiceLogin();
  if (new URLSearchParams(location.search).get('wake') && as.has_voice) setTimeout(voiceLogin, 500);
}

async function voiceLogin() {
  const msg = $('#login-msg');
  $('#app').classList.remove('hidden'); $('#app').classList.add('locked'); $('#boot').classList.add('fade');
  setState('listening'); setOrbMode('photo', { label: 'OUVINDO — DIGA A SUA FRASE' }); $('#caption').textContent = 'Diga a sua frase…';
  try {
    const v = await captureVoice();
    setState('thinking'); setOrbMode('photo', { label: 'ANALISANDO SUA VOZ' }); $('#caption').textContent = 'Analisando sua voz…';
    await sleep(1500);
    token = (await post('/api/auth/voice/login', { audio: v.audio, vector: v.vector })).token;
    setOrbMode('photo', { label: 'VOZ RECONHECIDA', result: 'ok' }); $('#caption').textContent = 'Voz reconhecida.';
    await sleep(1100); enter();
  } catch (e) {
    setOrbMode('photo', { label: 'VOZ NÃO RECONHECIDA', result: 'fail' }); $('#caption').textContent = 'Não reconheci a sua voz.';
    await sleep(1800); setOrbMode(null); setState('idle');
    $('#app').classList.add('hidden'); $('#app').classList.remove('locked'); $('#boot').classList.remove('fade');
    msg.textContent = (e.message && /não ouvi|Permission|NotAllowed|NotFound/i.test(e.message + e.name)) ? 'Não consegui ouvir (microfone?). Tente de novo ou use a senha.' : 'Voz não reconhecida. Tente de novo ou use a senha.';
  }
}

async function enter() {
  const focoPedido = !!new URLSearchParams(location.search).get('foco');   // aberta pelas palmas
  $('#boot').classList.add('out'); setTimeout(() => $('#boot').classList.add('hidden'), 1000);
  $('#app').classList.remove('hidden');
  try { log = (await api('/api/history')).map(m => ({ role: m.role, text: m.content })); } catch (e) {}
  connect(); setTab('chat', true); $('#app').classList.remove('locked'); $('#boot').classList.remove('fade'); setOrbMode(null);
  if (focoPedido) setFocus(true);
  const h = new Date().getHours();
  const hi = h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite';
  await sleep(900);
  const resumoP = store.get('brief', true) ? api('/api/briefing').catch(() => null) : null;
  say(hasVoice ? `${hi}. Kyky online e pronta.` : `${hi}. Kyky online. Ainda não conheço a sua voz, cadastre em Ajustes quando quiser.`);
  document.querySelectorAll('#side button').forEach(b => b.onclick = () => setTab(b.dataset.tab));
  if (resumoP) {
    await sleep(600); while (talking) await sleep(300);
    setState('thinking'); setOrbMode('glyph', { glyph: '📬', label: 'VERIFICANDO SEUS AVISOS' });
    const r = await resumoP; setOrbMode(null);
    if (r && r.text) { const tx = plain(r.text); pushLog('assistant', tx); say(tx); } else setState('idle');
  }
}

/* ---------------- WebSocket ---------------- */
// links externos abrem no navegador PADRÃO do Windows (Brave, Chrome...), não dentro da janela do app
async function openExt(url) { try { await post('/api/open', { url }); } catch (e) { window.open(url, '_blank', 'noopener'); } }
let wsTries = 0;
const touched = new Set();
const TOOLTAB = { search_leads: 'leads', queue_outreach: 'leads', search_jobs: 'jobs', prepare_application: 'jobs', add_task: 'tasks', complete_task: 'tasks' };
function openTouched() {
  const t = [...touched].map(n => TOOLTAB[n]).filter(Boolean).pop(); touched.clear();
  if (t) { tab = t; setTab(t); if (!$('#drawer').classList.contains('open')) setTab(t); }
}
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(token)}`);
  ws.onopen = () => { wsTries = 0; };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === 'tool') { setTool(m.name); touched.add(m.name); }
    else if (m.type === 'answer') { setOrbMode(null); const tx = plain(m.text); pushLog('assistant', tx); say(tx); $('#subcaption').textContent = 'via ' + m.provider; openTouched(); }
    else if (m.type === 'confirm') askConfirm(m);
    else if (m.type === 'focus') setFocus(!focus);
    else if (m.type === 'error') { setOrbMode(null); $('#subcaption').textContent = '⚠ ' + m.text; setState('idle'); }
    else if (m.type === 'idle') { busy = false; setOrbMode(null); if (!speaking) setState('idle'); resumeListening(); }
  };
  ws.onclose = ev => {
    if (!token) return;
    if (busy) { busy = false; setState('idle'); }   // a resposta em andamento se perdeu: não deixa o microfone travado
    if (ev.code === 4401) { token = null; location.reload(); return; }   // sessão inválida (servidor reiniciou)
    wsTries = Math.min(wsTries + 1, 6); $('#subcaption').textContent = 'conexão perdida, reconectando…';
    setTimeout(connect, 1000 * wsTries);
  };
}
const plain = t => String(t || '').replace(/```[\s\S]*?```/g, '').replace(/[\p{Extended_Pictographic}\p{Regional_Indicator}\u200d\ufe0f]/gu, '')
  .replace(/^\s{0,3}#{1,6}\s*/gm, '').replace(/(\*\*|__|`|~~)/g, '').replace(/^\s*[-*•]\s+/gm, '').replace(/^\s*\d+[.)]\s+/gm, '')
  .replace(/#(\d+)/g, 'número $1').replace(/\n{3,}/g, '\n\n').trim();
function sendText(t) {
  t = t.trim(); if (!t || busy) return;
  if (!ws || ws.readyState !== 1) { $('#subcaption').textContent = 'ainda conectando… tente de novo em um instante'; return false; }
  busy = true; pushLog('user', t); $('#caption').textContent = '“' + t + '”'; $('#subcaption').textContent = '';
  setState('thinking'); stopSpeaking();
  ws.send(JSON.stringify({ type: 'chat', text: t, level: $('#t-fast').checked ? 'fast' : 'strong' }));
}
function pushLog(role, text) { log.push({ role, text }); if (tab === 'chat') renderTab(); }

/* ---------------- Voz: fala (TTS) ---------------- */
function cleanSpeech(t) {
  return t.replace(/```[\s\S]*?```/g, ' código ').replace(/https?:\/\/\S+/g, ' link ').replace(/#(\d+)/g, 'número $1').replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/[\p{Extended_Pictographic}\p{Regional_Indicator}‍️⃣]/gu, '')
    .replace(/\bkyky\b/gi, 'Quiqui').replace(/\b(?:[sk]*k{2,}[sk]*|(?:sk){2,}k*|(?:ha|he|rs){2,}h*)\b/gi, '')
    .replace(/[*_#`>|~]/g, '').replace(/\s*[—–]\s*/g, ', ').replace(/\.{2,}|…/g, '.')
    .replace(/\n+/g, '. ').replace(/\s+/g, ' ').trim().slice(0, 900);
}
const FEM = /francisca|thalita|maria|fernanda|luciana|camila|vit[oó]ria|helo[ií]sa|raquel|yara|leila|let[ií]cia|giovanna|manuela|elza|\bana\b|female|feminin/i;
const MALE = /ant[oô]nio|daniel|felipe|donato|humberto|j[uú]lio|f[aá]bio|val[eé]rio|nicolau|leonardo|thiago|augusto|ricardo|jorge|paulo|pedro|\bmale\b|masculin/i;
function scoreVoice(v) {
  let s = 0;
  if (/pt[-_]BR/i.test(v.lang)) s += 40; else if (/^pt/i.test(v.lang)) s += 10; else return -999;
  if (/natural|online/i.test(v.name)) s += 100;
  if (FEM.test(v.name)) s += 60;
  if (MALE.test(v.name)) s -= 120;
  return s;
}
function ptVoices() { return speechSynthesis.getVoices().filter(v => scoreVoice(v) > -999).sort((a, b) => scoreVoice(b) - scoreVoice(a)); }
function pickVoice() {
  const vs = ptVoices(), want = store.get('voice', '');
  return vs.find(v => v.name === want) || vs[0] || null;
}
function chunks(t) {
  const out = []; let cur = '';
  for (const p of t.split(/(?<=[.!?])\s+/)) { if ((cur + ' ' + p).length > 260 && cur) { out.push(cur); cur = p; } else cur = cur ? cur + ' ' + p : p; }
  if (cur) out.push(cur); return out;
}
let vctx = null, vAn = null, vEl = null, vData = null, neural = false, speakToken = 0;
function initVoiceAudio() {
  if (vEl) return;
  vEl = new Audio(); vctx = new (window.AudioContext || window.webkitAudioContext)();
  const src = vctx.createMediaElementSource(vEl); vAn = vctx.createAnalyser(); vAn.fftSize = 512;
  src.connect(vAn); vAn.connect(vctx.destination); vData = new Uint8Array(vAn.fftSize);
}
async function fetchTts(txt) {
  const pct = Math.round((store.get('rate', 1.08) - 1) * 100);
  const r = await fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
    body: JSON.stringify({ text: txt, voice: store.get('tts', 'pt-BR-FranciscaNeural'), rate: (pct >= 0 ? '+' : '') + pct + '%' }) });
  if (!r.ok) throw new Error('tts ' + r.status);
  return URL.createObjectURL(await r.blob());
}
function endSpeech() { talking = false; speaking = false; neural = false; setState(busy ? 'thinking' : 'idle'); resumeListening(); }
async function speakNeural(parts, tk) {
  initVoiceAudio(); await vctx.resume();
  const jobs = parts.map(fetchTts); jobs.forEach(j => j.catch(() => {}));
  for (let k = 0; k < parts.length; k++) {
    let url; try { url = await jobs[k]; } catch (e) { if (k === 0) throw e; continue; }
    if (tk !== speakToken) return;
    vEl.src = url; await vEl.play();
    speaking = true; neural = true; setState('speaking');
    await new Promise(res => { vEl.onended = vEl.onerror = res; });
    if (tk !== speakToken) return;
  }
  endSpeech();
}
function speakBrowser(parts) {
  const v = pickVoice();
  parts.forEach((txt, i) => {
    const u = new SpeechSynthesisUtterance(txt); if (v) u.voice = v; u.lang = 'pt-BR'; u.rate = store.get('rate', 1.08) + 0.04; u.pitch = 1.1;
    if (i === 0) u.onstart = () => { speaking = true; setState('speaking'); };
    u.onboundary = () => { target = 1; };
    if (i === parts.length - 1) u.onend = u.onerror = endSpeech;
    speechSynthesis.speak(u);
  });
}
async function say(text) {
  $('#caption').textContent = text.length > 280 ? text.slice(0, 280) + '…' : text;
  if (!$('#t-speak').checked) { setState('idle'); return; }
  stopSpeaking(); stopListening(); talking = true;
  const parts = chunks(cleanSpeech(text)); if (!parts.length) { talking = false; setState('idle'); return; }
  const tk = ++speakToken;
  if (store.get('tts', 'pt-BR-FranciscaNeural') !== 'browser') {
    try { await speakNeural(parts, tk); return; } catch (e) { if (tk !== speakToken) return; }
  }
  if ('speechSynthesis' in window) speakBrowser(parts); else { talking = false; setState('idle'); }
}
function stopSpeaking() {
  speakToken++; try { speechSynthesis.cancel(); } catch (e) {} try { vEl && vEl.pause(); } catch (e) {}
  speaking = false; neural = false; talking = false;
}

/* ---------------- Voz: escuta (grava e o servidor transcreve com Whisper) ---------------- */
const ALUCINA = new Set(['obrigado', 'obrigada', 'tchau', 'ate a proxima', 'legendas pela comunidade amaraorg', 'tchau tchau', 'e ai']);
let recAbort = null;
function toB64(blob) { return new Promise(r => { const f = new FileReader(); f.onloadend = () => r(String(f.result).split(',')[1]); f.readAsDataURL(blob); }); }
async function recordUtterance({ maxMs = 15000, waitMs = 7000, silenceMs = 1100 } = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const ctx = new (window.AudioContext || window.webkitAudioContext)(), an = ctx.createAnalyser();
  an.fftSize = 2048; an.smoothingTimeConstant = 0; ctx.createMediaStreamSource(stream).connect(an);
  const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
  const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined), parts = [];
  mr.ondataavailable = e => { if (e.data.size) parts.push(e.data); };
  const td = new Uint8Array(an.fftSize), bins = new Float32Array(an.frequencyBinCount), hz = ctx.sampleRate / an.fftSize, NB = 32;
  const edges = Array.from({ length: NB + 1 }, (_, i) => 100 * Math.pow(40, i / NB));
  // limiar adaptativo: mede o ruído do ambiente nos primeiros 300ms (microfones de notebook costumam ser baixos)
  const frames = []; let started = false, lastLoud = 0, t0 = performance.now(), tStart = 0, aborted = false, noise = 0, nNoise = 0, thr = 0.03;
  mr.start(250);
  return new Promise(resolve => {
    const finish = () => {
      clearInterval(iv); stopMeterTarget();
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop()); ctx.close();
        const dur = started ? lastLoud - tStart : 0;
        if (!started || dur < 250) return resolve({ audio: null });
        const top = Math.max(...frames.map(f => f.e)), good = frames.filter(f => f.e > top - 10), mean = Array(NB).fill(0);
        good.forEach(f => f.v.forEach((x, i) => { mean[i] += x / good.length; }));
        const avg = mean.reduce((a, b) => a + b, 0) / NB;
        resolve({ audio: await toB64(new Blob(parts, { type: 'audio/webm' })), vector: mean.map(x => x - avg), dur });
      };
      if (mr.state !== 'inactive') mr.stop(); else mr.onstop();
    };
    const iv = setInterval(() => {
      an.getByteTimeDomainData(td); let m = 0; for (const x of td) m = Math.max(m, Math.abs(x - 128));
      const lvl = m / 128, now = performance.now(); target = Math.min(1, lvl * 2.5);
      if (!started && now - t0 < 300) { noise = (noise * nNoise + lvl) / ++nNoise; thr = Math.min(0.06, Math.max(0.015, noise * 2.5)); }
      else if (lvl > thr) {
        lastLoud = now; if (!started) { started = true; tStart = now; }
        an.getFloatFrequencyData(bins);
        const v = []; for (let b = 0; b < NB; b++) { let sum = 0, n = 0; for (let k = Math.floor(edges[b] / hz); k <= Math.floor(edges[b + 1] / hz) && k < bins.length; k++) { sum += Math.max(bins[k], -120); n++; } v.push(n ? sum / n : -120); }
        frames.push({ e: v.reduce((a, b) => a + b, 0) / NB, v });
      }
      if (aborted || (started && now - lastLoud > silenceMs) || (!started && now - t0 > waitMs) || now - t0 > maxMs) finish();
    }, 50);
    recAbort = () => { aborted = true; };
  });
}
function stopMeterTarget() { target = 0; }
async function captureVoice() {
  const r = await recordUtterance({ maxMs: 9000, waitMs: 6000, silenceMs: 1000 });
  if (!r.audio) throw new Error('não ouvi nada');
  return r;
}
async function startListening(manual) {
  if (!token) return;
  if (busy && manual) { $('#subcaption').textContent = 'ainda estou pensando na resposta anterior…'; return; }
  if (manual && talking) stopSpeaking();   // clicar no microfone interrompe a fala da Kyky
  if (listening || busy || talking) return;
  stopSpeaking(); listening = true; setState('listening'); $('#mic').classList.add('on');
  if (manual) $('#subcaption').textContent = 'pode falar…';
  let r = null;
  try { r = await recordUtterance(); }
  catch (e) { $('#subcaption').textContent = 'Sem acesso ao microfone (' + (e.name || e.message) + '). Libere o microfone para a Kyky.'; }
  listening = false; recAbort = null; $('#mic').classList.remove('on'); if (state === 'listening') setState('idle');
  if (r && !r.audio && manual) $('#subcaption').textContent = 'Não ouvi nada. Fale mais perto do microfone (ou confira se é o microfone certo no Windows).';
  if (r && r.audio) {
    setState('thinking'); $('#caption').textContent = 'entendendo…';
    try {
      const t = (await post('/api/stt', { audio: r.audio })).text;
      const n = norm(t);
      if (n.length > 1 && !ALUCINA.has(n)) { sendText(t); return; }
      $('#caption').textContent = ''; setState('idle');
    } catch (e) { $('#subcaption').textContent = 'Não consegui entender o áudio (' + e.message + ').'; setState('idle'); }
  }
  resumeListening();
}
function stopListening() { if (recAbort) recAbort(); }
function resumeListening() { if ($('#t-always') && $('#t-always').checked && !busy && !talking && !listening && token) setTimeout(startListening, 500); }
function norm(t) { return (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9 ]/g, '').trim(); }

/* ---------------- Confirmação de ação sensível ---------------- */
function askConfirm(m) {
  speechSynthesis.cancel(); setState('thinking');
  $('#confirm-text').textContent = m.text; $('#confirm-pw').value = ''; $('#confirm').classList.remove('hidden');
  $('#confirm-voice').classList.toggle('hidden', !!m.critical || !hasVoice);
  $('#confirm-note').textContent = m.critical ? 'Ação crítica: somente a senha aprova.' : '';
  $('#confirm-pw').focus();
  const close = () => $('#confirm').classList.add('hidden');
  const reply = o => { ws.send(JSON.stringify({ type: 'auth', id: m.id, critical: !!m.critical, ...o })); close(); };
  $('#confirm-ok').onclick = () => reply({ approve: true, password: $('#confirm-pw').value });
  $('#confirm-pw').onkeydown = e => { if (e.key === 'Enter') $('#confirm-ok').click(); };
  $('#confirm-no').onclick = () => reply({ approve: false });
  $('#confirm-voice').onclick = async () => {
    $('#confirm-note').textContent = 'Diga a sua frase…';
    try { const v = await captureVoice(); reply({ approve: true, voice: { audio: v.audio, vector: v.vector } }); }
    catch (e) { $('#confirm-note').textContent = 'Não consegui ouvir. Use a senha.'; }
  };
}

/* ---------------- Painéis laterais ---------------- */
const TITLES = { chat: 'Conversa', tasks: 'Tarefas', canvas: 'Canvas', leads: 'Leads e contatos', reports: 'Relatórios', github: 'GitHub', jobs: 'Vagas', config: 'Ajustes' };
function setTab(t, keepClosed) {
  const same = t === tab && $('#drawer').classList.contains('open') && !keepClosed;
  tab = t; document.querySelectorAll('#side button').forEach(b => b.classList.toggle('active', b.dataset.tab === t));
  $('#drawer-title').textContent = TITLES[t];
  $('#drawer').classList.toggle('open', !same && !keepClosed);
  if (!same) renderTab();
}
$('#drawer-close').onclick = () => $('#drawer').classList.remove('open');
const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const inline = x => x.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
function md(t) {
  const out = []; let ul = false;
  for (const raw of String(t).split('\n')) {
    const l = esc(raw);
    if (/^\s*[-*] /.test(l)) { if (!ul) { out.push('<ul>'); ul = true; } out.push('<li>' + inline(l.replace(/^\s*[-*] /, '')) + '</li>'); continue; }
    if (ul) { out.push('</ul>'); ul = false; }
    if (/^#{1,6} /.test(l)) out.push('<h4>' + inline(l.replace(/^#+ /, '')) + '</h4>'); else if (l.trim()) out.push('<p>' + inline(l) + '</p>');
  }
  if (ul) out.push('</ul>'); return out.join('');
}
const empty = (t) => `<div class="empty">${t}</div>`;
const pill = (t, c) => `<span class="pill ${c || ''}">${esc(t)}</span>`;
const domain = u => { try { return new URL(u).hostname.replace('www.', ''); } catch (e) { return ''; } };
async function renderTab() {
  const b = $('#drawer-body');
  if (tab === 'chat') {
    b.innerHTML = log.slice(-60).map(m => `<div class="bubble ${m.role === 'user' ? 'user' : 'kyky'}"><small>${m.role === 'user' ? 'você' : 'kyky'}</small>${esc(plain(m.text))}</div>`).join('') || empty('Nada ainda. Fale com a Kyky ou escreva.');
    b.scrollTop = b.scrollHeight; return;
  }
  if (tab === 'config') return renderConfig(b);
  b.innerHTML = empty('carregando…');
  try {
    if (tab === 'tasks') {
      const rows = (await api('/api/tasks')).text.split('\n').map(l => l.match(/^#(\d+) \[( |x)\] (.*?)(?: \(prazo (.*)\))?$/)).filter(Boolean);
      b.innerHTML = rows.map(m => `<div class="card ${m[2] === 'x' ? 'done' : 'click'}" data-id="${m[1]}"><div class="row-flex"><span class="check">${m[2] === 'x' ? '✓' : ''}</span><div><div class="ct">${esc(m[3])}</div>${m[4] ? pill('prazo ' + m[4]) : ''}</div></div></div>`).join('')
        || empty('Nenhuma tarefa. Diga: “Kyky, anota entregar o trabalho sexta”.');
      b.querySelectorAll('.card.click').forEach(c => c.onclick = async () => { await post('/api/tasks/' + c.dataset.id + '/done'); renderTab(); });
    } else if (tab === 'canvas') {
      const rows = (await api('/api/canvas')).text.split('\n').map(l => l.split(' | ')).filter(r => r.length >= 4);
      const hoje = new Date();
      b.innerHTML = rows.map(r => {
        const [d, mth] = r[0].split(' ')[0].split('/').map(Number), alvo = new Date(hoje.getFullYear(), mth - 1, d), dias = Math.ceil((alvo - hoje) / 864e5);
        return `<div class="card click" data-u="${esc(r[3])}"><div class="row-flex"><div class="datebox ${dias <= 2 ? 'hot' : ''}"><b>${esc(r[0].split(' ')[0])}</b><small>${esc(r[0].split(' ')[1] || '')}</small></div><div><div class="ct">${esc(r[2])}</div><div class="meta">${esc(r[1].split(' - ')[0])}</div></div></div></div>`;
      }).join('') || empty('Nada pendente no Canvas pelos próximos 30 dias.');
      b.querySelectorAll('.card.click').forEach(c => c.onclick = () => openExt(c.dataset.u));
    } else if (tab === 'github') {
      const rows = (await api('/api/github')).text.split('\n').map(l => l.split(' | ')).filter(r => r.length >= 3);
      b.innerHTML = rows.map(r => `<div class="card click" data-u="https://github.com/${esc(r[0])}"><div class="ct">${esc(r[0].split('/')[1] || r[0])}</div><div class="meta">${esc(r[0].split('/')[0])}</div><div style="margin-top:6px">${pill(r[1], r[1] === 'privado' ? 'warn' : '')} ${pill(r[2])}</div></div>`).join('') || empty('Sem repositórios (ou token do GitHub ausente).');
      b.querySelectorAll('.card.click').forEach(c => c.onclick = () => openExt(c.dataset.u));
    } else if (tab === 'leads') {
      const items = (await api('/api/outreach')).items;
      b.innerHTML = '<p class="hint">Peça: “Kyky, busque barbearias sem site em Betim”. Os leads caem aqui prontos para o WhatsApp.</p>' + (items.map(l => `
        <div class="card" data-id="${l.id}"><div class="row-flex" style="justify-content:space-between"><div class="ct">${esc(l.name)}</div>${pill(l.score, l.score >= 70 ? 'good' : 'warn')}</div>
        <div class="meta">${esc(l.address || '')}</div><div style="margin:6px 0">${pill('+' + l.phone)} ${pill(l.status, l.status === 'pendente' ? '' : 'good')}</div>
        <div class="btns"><button class="btn small wa">WHATSAPP</button><button class="btn small ghost done">ENVIADO</button><button class="btn small ghost danger skip">DESCARTAR</button></div></div>`).join('') || empty('Nenhum lead ainda.'));
      b.querySelectorAll('.card').forEach(c => {
        const id = c.dataset.id;
        c.querySelector('.wa').onclick = async () => openExt((await api('/api/outreach/' + id + '/link')).url);
        c.querySelector('.done').onclick = async () => { await post('/api/outreach/' + id + '/status', { status: 'enviado' }); renderTab(); };
        c.querySelector('.skip').onclick = async () => { await post('/api/outreach/' + id + '/status', { status: 'descartado' }); renderTab(); };
      });
    } else if (tab === 'jobs') {
      const items = (await api('/api/jobs')).items;
      b.innerHTML = '<p class="hint">Peça: “Kyky, busque vagas de estágio em TI”. Clique numa vaga para ver a candidatura preparada. Você revisa e envia.</p>' + (items.map(j => `
        <div class="card click" data-id="${j.id}"><div class="ct">${esc(j.title)}</div><div class="meta">${esc(domain(j.url))}</div><div style="margin-top:6px">${pill(j.status, j.status === 'preparada' ? 'good' : '')}</div></div>`).join('') || empty('Nenhuma vaga ainda.'));
      b.querySelectorAll('.card.click').forEach(c => c.onclick = async () => {
        b.innerHTML = empty('preparando a candidatura…');
        let r = await api('/api/jobs/' + c.dataset.id + '/application');
        if (r.text.startsWith('(ainda')) { await post('/api/jobs/' + c.dataset.id + '/prepare'); r = await api('/api/jobs/' + c.dataset.id + '/application'); }
        b.innerHTML = `<div class="btns"><button class="btn small" id="jopen">ABRIR A VAGA</button><button class="btn small ghost" id="jback">VOLTAR</button></div><div class="doc">${md(r.text)}</div>`;
        $('#jopen').onclick = () => openExt(r.url); $('#jback').onclick = renderTab;
      });
    } else if (tab === 'reports') {
      const list = await api('/api/reports');
      b.innerHTML = '<button id="gen" class="btn small" style="margin-bottom:12px">GERAR RELATÓRIO DE HOJE</button>' + (list.map(n => `<div class="card click" data-n="${n}"><div class="ct">${n.replace('.md', '').split('-').reverse().join('/')}</div><div class="meta">relatório diário</div></div>`).join('') || empty('Nenhum relatório ainda.'));
      $('#gen').onclick = async function () { this.textContent = 'GERANDO…'; this.disabled = true; try { await post('/api/daily'); } catch (e) {} renderTab(); };
      b.querySelectorAll('.card.click').forEach(c => c.onclick = async () => { b.innerHTML = '<div class="btns"><button class="btn small ghost" id="rback">VOLTAR</button></div><div class="doc">' + md((await api('/api/reports/' + c.dataset.n)).text) + '</div>'; $('#rback').onclick = renderTab; });
    }
  } catch (e) { b.innerHTML = empty('erro: ' + esc(e.message)); }
}
async function renderConfig(b) {
  const has = !!(await idbGet('theme'));
  const voices = ptVoices(), hasFace = !!(await idbGet('face'));
  b.innerHTML = `
  <div class="field"><label>Música de abertura</label>
    <input type="file" id="cf-music" accept="audio/*">
    <small>${has ? '✔ música definida' : 'nenhuma música escolhida'} — toca no modo foco (2 palmas ou 3 estalos de dedo liga e desliga).</small>
    <div class="row"><button class="btn small" id="cf-test">TESTAR</button><button class="btn small ghost" id="cf-clear">REMOVER</button></div></div>
  <div class="field"><label>Volume da música</label><input type="range" id="cf-vol" min="0" max="1" step="0.05" value="${store.get('vol', 0.7)}"></div>
  <div class="field"><label>Sua foto (aparece na esfera)</label>
    <input type="file" id="cf-face" accept="image/*"><small>${hasFace ? '✔ foto definida' : 'nenhuma foto'} — aparece enquanto a Kyky analisa a sua voz.</small></div>
  <div class="field"><label>Resumo ao abrir</label><label style="text-transform:none;letter-spacing:0;font-size:13px;color:var(--text)"><input type="checkbox" id="cf-brief" ${store.get('brief', true) ? 'checked' : ''}> A Kyky fala como estão seus emails, prazos e mensagens quando você entra</label></div>
  <div class="field"><label>Velocidade da fala</label><input type="range" id="cf-rate" min="0.8" max="1.4" step="0.02" value="${store.get('rate', 1.08)}"></div>
  <div class="field"><label>Voz da Kyky</label><select id="cf-voice" class="btn" style="width:100%;text-transform:none">${[['pt-BR-FranciscaNeural', 'Francisca — natural, feminina'], ['pt-BR-ThalitaMultilingualNeural', 'Thalita — natural, feminina'], ['browser', 'Voz do navegador (reserva)']].map(([v, n]) => `<option value="${v}" ${v === store.get('tts', 'pt-BR-FranciscaNeural') ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
  <div class="field"><label>Login por voz</label>
    <input type="text" id="cf-phrase" placeholder="frase secreta, ex: kyky acorda" value="kyky, acorda">
    <small>${hasVoice ? '✔ voz cadastrada. ' : ''}Grave 3 vezes a mesma frase. A voz é uma conveniência: pode ser imitada ou gravada, por isso ações críticas (como deploy) sempre exigem a senha.</small>
    <div class="row"><button class="btn small" id="cf-enroll">CADASTRAR MINHA VOZ</button></div><p class="msg" id="cf-msg"></p></div>`;
  $('#cf-music').onchange = async e => { if (e.target.files[0]) { await idbPut('theme', e.target.files[0]); renderTab(); } };
  $('#cf-face').onchange = async e => { if (e.target.files[0]) { await idbPut('face', e.target.files[0]); await loadFace(); renderTab(); } };
  $('#cf-brief').onchange = e => store.set('brief', e.target.checked);
  $('#cf-rate').oninput = e => store.set('rate', +e.target.value);
  $('#cf-test').onclick = () => playTheme(false); $('#cf-clear').onclick = async () => { await idbDel('theme'); renderTab(); };
  $('#cf-vol').oninput = e => { store.set('vol', +e.target.value); $('#theme').volume = +e.target.value; };
  $('#cf-voice').onchange = e => { store.set('tts', e.target.value); say('Olá, esta é a minha voz. Sou a Kyky.'); };
  $('#cf-enroll').onclick = async () => {
    const ph = $('#cf-phrase').value.trim(), msg = $('#cf-msg'); if (!ph) { msg.textContent = 'Escreva a frase primeiro.'; return; }
    const samples = []; msg.style.color = 'var(--amber)';
    try {
      for (let i = 1; i <= 3; i++) {
        msg.textContent = `Gravação ${i}/3 — diga: “${ph}”`; const v = await captureVoice();
        samples.push({ audio: v.audio, vector: v.vector }); msg.textContent = 'ok, aguarde…'; await sleep(900);
      }
      const r = await post('/api/auth/voice/enroll', { phrase: ph, samples });
      hasVoice = true; msg.style.color = 'var(--green)'; msg.textContent = '✔ Voz cadastrada. Entendi: ' + (r.ouvi || []).join(' | ');
    } catch (e) { msg.style.color = 'var(--amber)'; msg.textContent = 'Falhou: ' + e.message; }
  };
}

/* ---------------- Orbe ---------------- */
/* ---------------- Esfera: foto, carregamento e atividade ---------------- */
const TOOLINFO = {
  web_search: ['🌐', 'PESQUISANDO NA WEB'], fetch_url: ['📄', 'LENDO A PÁGINA'],
  canvas_courses: ['🎓', 'CONSULTANDO O CANVAS'], canvas_upcoming: ['🎓', 'CONSULTANDO O CANVAS'],
  github_repos: ['⌘', 'CONSULTANDO O GITHUB'], github_tree: ['⌘', 'LENDO O REPOSITÓRIO'], github_grep: ['⌘', 'PROCURANDO NO CÓDIGO'], github_patch: ['🛠', 'PREPARANDO A CORREÇÃO'], github_read: ['⌘', 'LENDO O REPOSITÓRIO'], github_status: ['⌘', 'CONSULTANDO O GITHUB'], github_deploy: ['🚀', 'PUBLICANDO NO GITHUB'],
  search_leads: ['📍', 'BUSCANDO LEADS'], build_site: ['🛠', 'MONTANDO O SITE'],
  queue_outreach: ['📨', 'ORGANIZANDO CONTATOS'], list_outreach: ['📨', 'ORGANIZANDO CONTATOS'], whatsapp_link: ['📨', 'ORGANIZANDO CONTATOS'], mark_outreach: ['📨', 'ORGANIZANDO CONTATOS'],
  add_task: ['✓', 'ATUALIZANDO TAREFAS'], list_tasks: ['✓', 'LENDO TAREFAS'], complete_task: ['✓', 'ATUALIZANDO TAREFAS'],
  list_files: ['🗂', 'LENDO ARQUIVOS'], read_file: ['🗂', 'LENDO ARQUIVOS'], write_file: ['🗂', 'ESCREVENDO ARQUIVO'], run_python: ['⚙', 'EXECUTANDO CÓDIGO'],
};
let orbMode = null, faceImg = null;
function setOrbMode(kind, o = {}) {
  orbMode = kind ? { kind, label: '', result: null, ...o } : null;
  if (orbMode && orbMode.label) $('#subcaption').textContent = orbMode.label;
}
function setTool(name) { const [g, l] = TOOLINFO[name] || ['⚙', 'TRABALHANDO']; setOrbMode('glyph', { glyph: g, label: l }); }
async function loadFace() {
  const b = await idbGet('face');
  const im = new Image(); im.onload = () => { faceImg = im; }; im.src = b ? URL.createObjectURL(b) : '/face.jpg';
}
function drawOrbOverlay(cx, mx, my, R, t, col) {
  const th = state === 'thinking';
  if (orbMode && orbMode.kind === 'photo' && faceImg) {
    cx.save(); cx.beginPath(); cx.arc(mx, my, R * 0.94, 0, 6.283); cx.clip();
    const sc = (R * 2) / Math.min(faceImg.width, faceImg.height), w = faceImg.width * sc, h = faceImg.height * sc;
    cx.globalAlpha = 0.92; cx.drawImage(faceImg, mx - w / 2, my - h / 2, w, h); cx.globalAlpha = 1;
    const sy = my - R + ((t * 0.9) % 1) * R * 2, gr = cx.createLinearGradient(0, sy - 26, 0, sy + 2);
    gr.addColorStop(0, col(0)); gr.addColorStop(1, col(0.55)); cx.fillStyle = gr; cx.fillRect(mx - R, sy - 26, R * 2, 28);
    cx.restore();
  } else if (orbMode && orbMode.kind === 'glyph') {
    cx.font = `${R * 0.75}px "Segoe UI Emoji","Segoe UI Symbol",sans-serif`; cx.textAlign = 'center'; cx.textBaseline = 'middle';
    cx.fillStyle = col(1); cx.fillText(orbMode.glyph, mx, my + R * 0.04);
  }
  if (orbMode || th) {
    const res = orbMode && orbMode.result;
    cx.lineWidth = 5; cx.lineCap = 'round'; cx.beginPath();
    if (res) { cx.strokeStyle = res === 'ok' ? 'rgb(53,255,168)' : 'rgb(255,84,104)'; cx.shadowColor = cx.strokeStyle; cx.shadowBlur = 18; cx.arc(mx, my, R * 1.12, 0, 6.283); }
    else { cx.strokeStyle = col(1); cx.shadowColor = col(1); cx.shadowBlur = 14; const a = t * 3.4; cx.arc(mx, my, R * 1.12, a, a + 1.9 + Math.sin(t * 2) * 0.5); }
    cx.stroke(); cx.shadowBlur = 0; cx.lineCap = 'butt';
  }
}
const COLORS = { idle: [53, 224, 255], listening: [53, 255, 168], thinking: [255, 182, 46], speaking: [160, 120, 255] };
const LABELS = { idle: 'EM ESPERA', listening: 'ESCUTANDO', thinking: 'PROCESSANDO', speaking: 'FALANDO' };
let cur = [...COLORS.idle];
function setState(s) { state = s; $('#state-chip').textContent = LABELS[s]; }
const cv = $('#orb'), cx = cv.getContext('2d');
const parts = Array.from({ length: 70 }, () => ({ a: Math.random() * 6.28, r: 1.05 + Math.random() * 0.55, s: (Math.random() - .5) * .006, z: Math.random() }));
let looping = false;
function loop() {
  looping = true;
  const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== W * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
  cx.setTransform(dpr, 0, 0, dpr, 0, 0); cx.clearRect(0, 0, W, H);
  const t = performance.now() / 1000, c = COLORS[state];
  for (let i = 0; i < 3; i++) cur[i] += (c[i] - cur[i]) * 0.06;
  if (state === 'speaking' && neural && vAn) { vAn.getByteTimeDomainData(vData); let m = 0; for (const x of vData) m = Math.max(m, Math.abs(x - 128)); target = Math.min(1, m / 38); }
  else if (state === 'speaking') target = Math.max(target * 0.9, 0.35 + 0.35 * Math.abs(Math.sin(t * 7) * Math.sin(t * 2.3)) + Math.random() * 0.15);
  else if (state === 'thinking') target = 0.22 + 0.1 * Math.sin(t * 5);
  else if (state === 'idle') target = 0.08 + 0.04 * Math.sin(t * 1.4);
  level += (target - level) * 0.18;
  const col = a => `rgba(${cur.map(Math.round).join(',')},${a})`;
  const R = Math.min(W, H) * 0.25, mx = W / 2, my = H / 2;
  // brilho
  let g = cx.createRadialGradient(mx, my, R * 0.2, mx, my, R * 1.95); g.addColorStop(0, col(0.28 + level * 0.3)); g.addColorStop(1, col(0));
  cx.fillStyle = g; cx.fillRect(0, 0, W, H);
  // anéis de orientação
  cx.lineWidth = 1;
  for (let k = 0; k < 3; k++) {
    cx.save(); cx.translate(mx, my); cx.rotate(t * (0.15 + k * 0.1) * (k % 2 ? -1 : 1));
    cx.strokeStyle = col(0.25 - k * 0.05); cx.setLineDash(k === 0 ? [4, 10] : k === 1 ? [30, 14] : [2, 6]);
    cx.beginPath(); cx.arc(0, 0, R * (1.55 + k * 0.17), 0, 6.283); cx.stroke(); cx.restore();
  }
  cx.setLineDash([]);
  // ondas
  for (let w = 0; w < 5; w++) {
    cx.beginPath();
    for (let i = 0; i <= 180; i++) {
      const th = i / 180 * 6.2832, amp = R * (0.03 + level * 0.30) * (1 - w * 0.13);
      const r = R * (1.05 + w * 0.045) + amp * Math.sin(th * (3 + w) + t * (1.6 + w * .5) + w) + amp * 0.5 * Math.sin(th * (7 - w) - t * 2.2);
      const x = mx + Math.cos(th) * r, y = my + Math.sin(th) * r; i ? cx.lineTo(x, y) : cx.moveTo(x, y);
    }
    cx.closePath(); cx.strokeStyle = col(0.75 - w * 0.13); cx.lineWidth = 1.6 - w * 0.2; cx.shadowColor = col(1); cx.shadowBlur = 12; cx.stroke();
  }
  cx.shadowBlur = 0;
  // esfera
  g = cx.createRadialGradient(mx - R * .3, my - R * .35, R * .1, mx, my, R);
  g.addColorStop(0, col(0.55)); g.addColorStop(0.6, col(0.3 + level * .25)); g.addColorStop(1, col(0.05));
  cx.fillStyle = g; cx.beginPath(); cx.arc(mx, my, R * (1 + level * 0.06), 0, 6.283); cx.fill();
  cx.strokeStyle = col(0.9); cx.lineWidth = 1.5; cx.stroke();
  // partículas
  for (const p of parts) { p.a += p.s * (1 + level * 6); const rr = R * p.r * (1 + level * .15), x = mx + Math.cos(p.a) * rr, y = my + Math.sin(p.a) * rr * (0.55 + p.z * 0.45);
    cx.fillStyle = col(0.3 + p.z * 0.6); cx.beginPath(); cx.arc(x, y, 1 + p.z * 1.6, 0, 6.283); cx.fill(); }
  drawOrbOverlay(cx, mx, my, R, t, col);
  requestAnimationFrame(loop);
}

/* ---------------- Eventos ---------------- */
$('#orb').onclick = () => { if (listening) stopListening(); else startListening(true); };
$('#mic').onclick = () => { if (listening) stopListening(); else startListening(true); };
$('#composer').onsubmit = e => { e.preventDefault(); const i = $('#text'); if (sendText(i.value) !== false) i.value = ''; };
$('#t-always').onchange = e => { if (e.target.checked) startListening(); else stopListening(); };
$('#t-speak').onchange = e => { if (!e.target.checked) stopSpeaking(); };
if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};
loadFace(); loop(); boot();
