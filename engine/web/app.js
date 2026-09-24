/* 551 Switchboard Simulator — the status page (game_control.md §7).
 *
 * The page never shows what it asked for, only what was echoed (§7.2). A tap
 * publishes a /set and changes nothing on screen; the display moves when the
 * game program's state topic moves. That is the same rule every other client
 * follows, and it is why there is no local model of the game here — only a
 * map of retained topic values, and a render that reads it.
 *
 * Host time, not the iPad's (§7.2). On the travel router neither clock may
 * have seen a time server, so every duration is computed against the host's
 * clock, whose offset from ours comes from each game_heartbeat.
 */
'use strict';

const PREFIX = 'sbgame/';
const STALE_MS = 2500;              // §7.2: 2.5 s without a heartbeat
const N_STATION_JACKS = 30, N_TRUNK_JACKS = 10;

// ---- state: retained topic values, and nothing else ------------------------

const S = Object.create(null);      // topic without the prefix -> payload
let client = null;
let brokerUp = false;
let hostOffset = 0;                 // host clock minus ours, seconds
let lastGameBeat = 0, lastEspBeat = 0;   // our clock, for staleness
let stopArmed = 0;                  // Stop needs a second tap within 3 s
let panelOpen = null;               // "station/7" while its panel is up
let nextEnabledAt = 0;              // Next Call re-enables after 3 s regardless

const get = (k) => S[k] || '';
const on = (k) => S[k] === 'on';
const hostNow = () => Date.now() / 1000 + hostOffset;
const num = (k) => { const v = parseFloat(get(k)); return isFinite(v) ? v : null; };

// ---- connection (§7.2) -----------------------------------------------------

function connect() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  // location.host, so no address, port or scheme is written into the page and
  // it works unchanged at home and on the road (§2).
  client = mqtt.connect(`${scheme}://${location.host}/mqtt`, {
    username: 'sbgame-web',
    password: 'PAGE_PASSWORD',      // replaced at install; see web/README.md
    clean: true,
    keepalive: 10,
    reconnectPeriod: 2000,
    connectTimeout: 8000,
  });

  client.on('connect', () => {
    brokerUp = true;
    // Retained topics give the whole state at once; there is nothing to request.
    client.subscribe(PREFIX + '#', { qos: 0 });
    render();
  });
  client.on('close', () => { brokerUp = false; render(); });
  client.on('error', () => { brokerUp = false; render(); });

  client.on('message', (topic, payload) => {
    const key = topic.startsWith(PREFIX) ? topic.slice(PREFIX.length) : topic;
    const text = payload.toString();

    if (key === 'ctl/game_heartbeat') {
      // The host's clock (§7.2). Keep the offset, not the time.
      const t = parseFloat(text);
      if (isFinite(t)) hostOffset = t - Date.now() / 1000;
      lastGameBeat = Date.now();
      return;                       // not state; nothing to store
    }
    if (key === 'ctl/esp_heartbeat') { lastEspBeat = Date.now(); return; }

    // A trunk's dialled digit is an event, not state (mqtt.md §7). The call
    // slot's `digits` and the log carry what the page missed while away.
    if (/^trunk\/\d+\/digit$/.test(key)) return;

    if (text === '') delete S[key]; else S[key] = text;
    render();
  });
}

// Safari closes the socket when the iPad locks or the page goes to the
// background. Reconnect at once on return rather than waiting for the timer.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && client && !client.connected) {
    client.reconnect();
  }
});

// ---- commands: the page publishes only sbgame/game/+/set -------------------

function send(name, value, qos) {
  if (!client || !client.connected) return;
  client.publish(`${PREFIX}game/${name}/set`, value, { qos: qos === undefined ? 1 : qos });
}

// ---- staleness (§7.2) ------------------------------------------------------
//
// Grey out rather than blank, so the operator sees the last known value and
// that it may be old, instead of an empty box that looks like "nothing there".

const gameStale = () =>
  !brokerUp || get('ctl/game_status') !== 'online' ||
  (lastGameBeat && Date.now() - lastGameBeat > STALE_MS);
const espStale = () =>
  !brokerUp || get('ctl/status') !== 'online' ||
  (lastEspBeat && Date.now() - lastEspBeat > STALE_MS);
const audioStale = () => !brokerUp || get('ctl/audio_status') !== 'online';

// ---- the board (§7.1) ------------------------------------------------------

const jackCircuit = (kind, n) => get(`board/${kind}/${n}/circuit`);
const jackLabel = (kind, n) => get(`board/${kind}/${n}/label`);

/** The label for a circuit id, from the board map — not a circuit number. */
function labelOf(circuit) {
  if (!circuit) return '';
  for (let n = 1; n <= N_STATION_JACKS; n++)
    if (jackCircuit('station', n) === circuit) return jackLabel('station', n) || circuit;
  for (let n = 1; n <= N_TRUNK_JACKS; n++)
    if (jackCircuit('trunk', n) === circuit) return `trunk ${n}`;
  return circuit;
}

/** One state per tile, most urgent first (§7.1's table). */
function tileState(kind, circuit) {
  if (!circuit) return 'none';
  const peer = get(`${circuit}/peer`);
  if (peer === 'ambiguous' || peer === 'deaf' || get(`${circuit}/play`) === 'missing'
      || on(`${circuit}/fault`)) return 'fault';
  if (on(`${circuit}/ring`)) return 'ringing';
  if (kind === 'station' && on(`${circuit}/hook`) && !on(`${circuit}/op`) && !peer)
    return 'calling';
  if (peer) return 'connected';
  if (on(`${circuit}/op`)) return 'operator';
  if (kind === 'station' ? on(`${circuit}/hook`) : on(`${circuit}/seize`)) return 'busy';
  return 'idle';
}

function renderBoard() {
  const el = document.getElementById('board');
  if (!el.dataset.built) {
    let html = '';
    for (let row = 0; row < 3; row++) {
      html += '<div class="row">';
      for (let n = row * 10 + 1; n <= row * 10 + 10; n++)
        html += `<div class="tile" id="j-station-${n}" data-kind="station" data-n="${n}"></div>`;
      html += '</div>';
    }
    html += '<div class="row trunks">';
    for (let n = 1; n <= N_TRUNK_JACKS; n++)
      html += `<div class="tile" id="j-trunk-${n}" data-kind="trunk" data-n="${n}"></div>`;
    html += '</div>';
    el.innerHTML = html;
    el.dataset.built = '1';
    el.addEventListener('click', (e) => {
      const t = e.target.closest('.tile');
      if (!t) return;
      const which = `${t.dataset.kind}/${t.dataset.n}`;
      // The same jack again closes it, so one finger opens and shuts a tile.
      if (panelOpen === which) closePanel();
      else showPanel(t.dataset.kind, +t.dataset.n);
    });
  }

  for (const kind of ['station', 'trunk']) {
    const count = kind === 'station' ? N_STATION_JACKS : N_TRUNK_JACKS;
    for (let n = 1; n <= count; n++) {
      const tile = document.getElementById(`j-${kind}-${n}`);
      const circuit = jackCircuit(kind, n);
      const state = tileState(kind, circuit);
      const peer = circuit ? get(`${circuit}/peer`) : '';
      const far = peer && peer !== 'ambiguous' && peer !== 'deaf' ? labelOf(peer) : '';
      // A jack with no circuit keeps its outline so the board keeps its shape.
      const label = kind === 'trunk' ? '' : (jackLabel(kind, n) || '');
      const cls = `tile s-${state}` + (circuit ? '' : ' empty') +
                  ((espStale() || audioStale()) ? ' stale' : '');
      const html = `<span class="jn">${n}</span>` +
                   (label ? `<span class="jl">${esc(label)}</span>` : '') +
                   (far ? `<span class="far">${esc(far)}</span>` : '');
      // Rewriting an unchanged tile restarts the ringing animation and throws
      // away any selection, twice a second.
      if (tile.className !== cls) tile.className = cls;
      if (tile.dataset.html !== html) { tile.innerHTML = html; tile.dataset.html = html; }
    }
  }
}

function closePanel() {
  document.getElementById('panel').hidden = true;
  panelOpen = null;
}

function showPanel(kind, n) {
  panelOpen = `${kind}/${n}`;
  const circuit = jackCircuit(kind, n);
  const p = document.getElementById('panel');
  const rows = [['jack', `${kind} ${n}`], ['circuit', circuit || '—'],
                ['label', jackLabel(kind, n) || '—']];
  if (circuit) {
    for (const f of (kind === 'station' ? ['hook', 'ring', 'peer', 'op', 'play', 'listen', 'fault']
                                        : ['seize', 'ring', 'peer', 'op', 'play', 'tone', 'listen', 'fault']))
      rows.push([f, get(`${circuit}/${f}`) || '—']);
    if (kind === 'trunk') rows.push(['dialled', get(`${circuit}/dialled`) || '—']);
    const using = [...occupiedSlots()].find(
      (s) => get(`game/call/${s}/trunk`) === circuit);
    rows.push(['in call', using ? get(`game/call/${using}/number`) : '—']);
  }
  document.getElementById('panel-body').innerHTML =
    `<h3>${esc(kind === 'trunk' ? `Trunk ${n}` : (jackLabel(kind, n) || `Jack ${n}`))}</h3>` +
    rows.map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(String(v))}</b></div>`).join('');
  p.hidden = false;

  // Next to the tile that was tapped, not parked in a corner: at this size the
  // board fills the screen and a panel in the corner is nowhere near the jack
  // it describes. Clamped so it never runs off an edge.
  const tile = document.getElementById(`j-${kind}-${n}`);
  const r = tile.getBoundingClientRect();
  const pr = p.getBoundingClientRect();
  const pad = 8;
  let left = r.left + r.width / 2 - pr.width / 2;
  let top = r.bottom + pad;
  if (top + pr.height > window.innerHeight - pad) top = r.top - pr.height - pad;
  if (top < pad) top = pad;
  p.style.left = `${Math.max(pad, Math.min(left, window.innerWidth - pr.width - pad))}px`;
  p.style.top = `${top}px`;
}
document.addEventListener('click', (e) => {
  if (!e.target.closest('.tile') && !e.target.closest('#panel')) closePanel();
});
// Escape, for the desktop browser Mark is using to look at this. There is no
// keyboard on the iPad, so it costs nothing there.
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && panelOpen) closePanel();
});

// ---- calls, health, log ----------------------------------------------------

function* occupiedSlots() {
  for (let s = 1; s <= 8; s++) if (get(`game/call/${s}/scene`)) yield s;
}

function renderCalls() {
  const body = document.querySelector('#calls tbody');
  const now = hostNow();
  const rows = [];
  for (const s of occupiedSlots()) {
    const g = (f) => get(`game/call/${s}/${f}`);
    const since = parseFloat(g('since')), dl = parseFloat(g('deadline'));
    const trunk = g('trunk');
    rows.push(`<tr><td>${esc(g('number'))}</td><td>${esc(g('scene'))}</td>` +
      `<td>${esc(g('from'))}</td><td>${esc(g('to') || 'operator')}</td>` +
      `<td>${trunk ? esc(labelOf(trunk)) : '—'}</td>` +
      `<td class="stage">${esc(g('stage'))}</td>` +
      `<td>${isFinite(since) ? secs(now - since) : '—'}</td>` +
      `<td>${isFinite(dl) ? secs(dl - now) : '—'}</td></tr>`);
  }
  body.innerHTML = rows.join('') ||
    '<tr class="none"><td colspan="8">no calls in progress</td></tr>';
}

function renderHealth() {
  const age = (t) => (t ? `${((Date.now() - t) / 1000).toFixed(1)}s` : '—');
  const src = get('audio/monitor/source');
  const rows = [
    ['controller', get('ctl/status') || '—', espStale()],
    ['esp beat', age(lastEspBeat), espStale()],
    ['i2c', get('ctl/i2c') || '—', espStale()],
    ['audio', get('ctl/audio_status') || '—', audioStale()],
    ['optone', get('audio/optone') || '—', audioStale()],
    ['monitor', get('audio/monitor') || '—', audioStale()],
    ['source', src === 'tap' ? 'tap' : (src ? labelOf(src) : '—'), audioStale()],
    ['game', get('ctl/game_status') || '—', gameStale()],
    ['game beat', age(lastGameBeat), gameStale()],
  ];
  document.getElementById('health').innerHTML = rows.map(
    ([k, v, stale]) => `<div class="${stale ? 'stale' : ''}"><span>${esc(k)}</span>` +
                       `<b>${esc(v)}</b></div>`).join('');
}

function renderTop() {
  document.getElementById('lamp-broker').className = 'lamp ' + (brokerUp ? 'up' : 'down');
  document.getElementById('lamp-game').className =
    'lamp ' + (get('ctl/game_status') === 'online' && !gameStale() ? 'up' : 'down');

  const running = get('game/run') === 'on';
  const auto = get('game/pace') === 'auto';
  const disabled = gameStale();

  document.getElementById('start').disabled = disabled || running;
  const stop = document.getElementById('stop');
  stop.disabled = disabled || !running;
  stop.textContent = stopArmed > Date.now() ? 'Stop — again' : 'Stop';
  stop.classList.toggle('armed', stopArmed > Date.now());

  document.getElementById('pace-manual').classList.toggle('sel', !auto);
  document.getElementById('pace-auto').classList.toggle('sel', auto);
  for (const b of ['pace-manual', 'pace-auto']) document.getElementById(b).disabled = disabled;

  const next = document.getElementById('next');
  next.disabled = disabled || !running || Date.now() < nextEnabledAt;
  next.classList.toggle('small', auto);

  document.getElementById('steppers').style.display = auto ? '' : 'none';
  for (const f of ['gap', 'ramp', 'floor'])
    document.getElementById('v-' + f).textContent = get('game/' + f) || '–';
  document.getElementById('v-gapnow').textContent = get('game/gap_now') || '–';
  const at = num('game/next_at');
  document.getElementById('v-countdown').textContent =
    at === null ? '–' : secs(at - hostNow());

  const t = { started: num('game/started') || 0, success: num('game/success') || 0,
              fail: num('game/fail') || 0 };
  const handled = t.success + t.fail;
  document.getElementById('t-started').textContent = t.started;
  document.getElementById('t-handled').textContent = handled;
  document.getElementById('t-success').textContent = t.success;
  document.getElementById('t-fail').textContent = t.fail;
  document.getElementById('t-pct').textContent =
    handled ? Math.round((t.success / handled) * 100) + '%' : '–';
  document.getElementById('t-prog').textContent = [...occupiedSlots()].length;

  document.getElementById('tallies').classList.toggle('stale', gameStale());
}

function render() {
  // Keep an open panel's values live: it reads the same topics as the board.
  if (panelOpen) {
    const [kind, n] = panelOpen.split('/');
    showPanel(kind, +n);
  }
  renderTop();
  renderBoard();
  renderCalls();
  renderHealth();
  const err = get('game/error');
  const e = document.getElementById('error');
  e.textContent = err;
  e.hidden = !err;
  const log = document.getElementById('log');
  // Only when it has actually changed. render() runs twice a second, and
  // rewriting textContent destroys any selection the user is making — which
  // is why dragging over the log appeared to clear it the moment you let go.
  const text = get('game/log');
  if (log.textContent !== text) log.textContent = text;
  log.classList.toggle('stale', gameStale());
  document.body.classList.toggle('offline', !brokerUp);
}

// ---- taps ------------------------------------------------------------------

document.getElementById('start').onclick = () => send('run', 'on');
document.getElementById('stop').onclick = () => {
  // §7.1: a second tap within 3 s, because Stop ends a player's game.
  if (stopArmed > Date.now()) { stopArmed = 0; send('run', 'off'); }
  else { stopArmed = Date.now() + 3000; setTimeout(render, 3100); }
  render();
};
document.getElementById('next').onclick = () => {
  // §4.1: QoS 0, never resent on reconnect, and the button disables itself
  // until `started` changes — or 3 s, so a lost tap does not leave it dead.
  send('next', '', 0);
  nextEnabledAt = Date.now() + 3000;
  setTimeout(render, 3100);
  render();
};
document.getElementById('pace-manual').onclick = () => send('pace', 'manual');
document.getElementById('pace-auto').onclick = () => send('pace', 'auto');
document.getElementById('steppers').addEventListener('click', (e) => {
  const spec = e.target.dataset.step;
  if (!spec) return;
  const [name, delta] = spec.split(':');
  const now = num('game/' + name);
  if (now === null) return;
  // §7.2: the steppers publish the new value, not a step. The game program
  // clamps and echoes what it applied.
  send(name, String(Math.max(0, now + parseFloat(delta))));
});

// `started` changing is what re-enables Next Call (§4.1).
let lastStarted = null;
setInterval(() => {
  const s = get('game/started');
  if (s !== lastStarted) { lastStarted = s; nextEnabledAt = 0; }
  render();                           // countdowns and ages tick on their own
}, 500);

// ---- small helpers ---------------------------------------------------------

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function secs(v) {
  if (!isFinite(v)) return '—';
  const n = Math.max(0, Math.round(v));
  return n >= 60 ? `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}` : `${n}s`;
}

// The page is installable and opens from the Home Screen without Safari's
// bars (game_control.md 7.3). The worker also opens it from cache, which
// matters when the iPad has been asleep and the board is wanted at once.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch((e) => {
      // Not fatal: without it the page is an ordinary page.
      console.warn('service worker not registered:', e);
    });
  });
}

connect();
render();
