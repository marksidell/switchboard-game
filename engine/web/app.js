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
const PHONE_STATION = 24;           // the real telephone (game_control.md Rev 73)

// ---- state: retained topic values, and nothing else ------------------------

const S = Object.create(null);      // topic without the prefix -> payload
let client = null;
let brokerUp = false;
let hostOffset = 0;                 // host clock minus ours, seconds
let lastGameBeat = 0, lastEspBeat = 0;   // our clock, for staleness
let stopArmed = 0;                  // Stop needs a second tap within 3 s
let panelOpen = null;               // "station/7" while its panel is up
let nextEnabledAt = 0;              // Next Call re-enables after 3 s regardless
let playSince = 0;                  // our clock when audio/playback last changed
// A circuit's `peer` going `deaf` or `ambiguous` is a fault only once it has
// stayed so for a second (§7.1, Rev 52): a relay or the cord switch breaks the
// line for about 0.2s, and the detector reports `deaf` for that long.
const PEER_FAULT_MS = 1000;
const peerFaultSince = Object.create(null);   // circuit -> our clock, ms
const peerBefore = Object.create(null);       // circuit -> the last other peer

// Whether this iPad shows the controls (§7.1, Rev 13). A preference of this
// device alone, so it lives in the browser and not on the bus. Shown unless
// hidden here: storage can come back empty, and an iPad that has lost its
// setting should be able to run the game.
const CONTROLS_KEY = 'sbgame.controls';
let showControls = true;
try { showControls = localStorage.getItem(CONTROLS_KEY) !== 'hidden'; } catch (e) { /* default */ }

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
    // Drop what we held first: a topic cleared while we were away, such as a
    // peer back from deaf, is not sent again (Rev 77).
    for (const k in S) delete S[k];
    for (const k in peerFaultSince) delete peerFaultSince[k];
    for (const k in peerBefore) delete peerBefore[k];
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

    const peerKey = /^((?:station|trunk)\/\d+)\/peer$/.exec(key);
    if (peerKey) {
      const c = peerKey[1];
      if (text === 'deaf' || text === 'ambiguous') {
        if (!(c in peerFaultSince)) { peerFaultSince[c] = Date.now(); peerBefore[c] = get(key); }
      } else {
        delete peerFaultSince[c];
      }
    }

    // When a playback began, by our clock, for its time (§7.7, Rev 61).
    if (key === 'audio/playback' && text !== get(key)) playSince = Date.now();

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

// ---- commands: the page publishes only sbgame/game/+/set, and the -----------
// ---- public-address service's look-now (mqtt.md 6.3) ----------------------

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
// The public address (§7.1, Rev 68): looked up every 5 min, so stale once
// the last lookup is over 11 min old — the service is down — or failed.
const IP_STALE_S = 660;
const ipStale = () => {
  const at = num('host/public_ip/checked');
  return !brokerUp || at === null || hostNow() - at > IP_STALE_S ||
    get('host/public_ip/error') !== '';
};
// The public trunk (§7.1, Rev 72): the trunk 8 ATA's registration, looked at
// every 10s, so stale — the service is down — after 30s.
const TRUNK_STALE_S = 30;
const trunkStale = () => {
  const at = num('host/public_trunk/checked');
  return at === null || hostNow() - at > TRUNK_STALE_S;
};
const trunkShown = () => {
  const v = get('host/public_trunk');
  return !v ? '—' : (trunkStale() ? 'error' : v);
};
let ipAsked = null;                  // `checked` when the line was tapped
let ipAskedAt = 0;

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

/** One state per tile, most urgent first (§7.1's table). A labelled jack with
 *  nothing cabled to it is drawn as a working jack at rest (Rev 11). */
function tileState(kind, circuit, label) {
  if (!circuit) return label ? 'idle' : 'none';
  // Station 24 is a real telephone: its own hook is `lifted`, and its `hook`
  // is the relay that puts the line on channel 24 (Rev 73).
  const offHook = kind === 'station' &&
    on(circuit === `station/${PHONE_STATION}` ? `${circuit}/lifted` : `${circuit}/hook`);
  let peer = get(`${circuit}/peer`);
  if (circuit in peerFaultSince && Date.now() - peerFaultSince[circuit] < PEER_FAULT_MS)
    peer = peerBefore[circuit];        // held, as the game holds it (§5)
  if (peer === 'ambiguous' || peer === 'deaf' || get(`${circuit}/play`) === 'missing'
      || on(`${circuit}/fault`)) return 'fault';
  if (on(`${circuit}/ring`)) return 'ringing';
  if (offHook && !on(`${circuit}/op`) && !peer)
    return 'calling';
  if (peer) return 'connected';
  if (on(`${circuit}/op`)) return 'operator';
  if (kind === 'station' ? offHook : on(`${circuit}/seize`)) return 'busy';
  return 'idle';
}

function renderBoard() {
  const el = document.getElementById('board');
  if (!el.dataset.built) {
    let html = '';
    // The 551's rows run 21-30, 11-20, 1-10 from the top (Rev 37).
    for (let row = 2; row >= 0; row--) {
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

  const labels = [];
  for (const kind of ['station', 'trunk']) {
    const count = kind === 'station' ? N_STATION_JACKS : N_TRUNK_JACKS;
    for (let n = 1; n <= count; n++) {
      const tile = document.getElementById(`j-${kind}-${n}`);
      const circuit = jackCircuit(kind, n);
      const label = kind === 'trunk' ? '' : (jackLabel(kind, n) || '');
      const state = tileState(kind, circuit, label);
      const peer = circuit ? get(`${circuit}/peer`) : '';
      const far = peer && peer !== 'ambiguous' && peer !== 'deaf' ? labelOf(peer) : '';
      // A jack with a label looks like a working jack whether or not a
      // circuit is cabled to it: the operator sees the board, not the wiring.
      // One with neither keeps its outline so the board keeps its shape.
      const shown = !!(circuit || label);
      // `lit` is every state that is not the board at rest. The stylesheet
      // uses it for the glow, so idle and empty jacks stay quiet.
      const cls = `tile s-${state}` + (shown ? '' : ' empty') +
                  (circuit && state !== 'idle' ? ' lit' : '') +
                  ((espStale() || audioStale()) ? ' stale' : '');
      const html = `<span class="jn">${n}</span>` +
                   (label ? `<span class="jl">${esc(label)}</span>` : '') +
                   // Always present, even empty. It is the line that says who
                   // the far end is, and it appears the moment a call
                   // connects - as a flex item that came and went it shoved
                   // the label up and down under a connecting tile. The
                   // stylesheet holds its height open whether it has text or
                   // not, so the label sits where it will stay.
                   (shown ? `<span class="far">${esc(far)}</span>` : '') +
                   // An unlabelled, uncabled jack has no lamp drawn: it is
                   // not part of the board the operator is shown.
                   (shown ? '<span class="cap"></span>' : '');
      // Rewriting an unchanged tile restarts the ringing animation and throws
      // away any selection, twice a second.
      if (tile.className !== cls) tile.className = cls;
      if (tile.dataset.html !== html) {
        tile.innerHTML = html;
        tile.dataset.html = html;
        const jl = tile.querySelector('.jl');
        if (jl) jl.style.fontSize = `${labelPx}px`;
      }
      labels.push(label);
    }
  }
  // Refitted only when the labels themselves change, not on every call: the
  // far-end line has its space held open whether it is empty or not, so a
  // call connecting cannot change what fits.
  const key = labels.join('\n');
  if (key !== labelsKey) { labelsKey = key; fitBoard(); }
}

/** One size for every label on the board: the largest at which the longest
 *  of them still fits its tile, so the board reads as one designation strip
 *  rather than a mixture of sizes. The stylesheet's size is the most any
 *  label gets. */
const LABEL_MAX_PX = 17, LABEL_MIN_PX = 10;
let labelPx = LABEL_MAX_PX;
let labelsKey = null;           // the labels last fitted, to refit on a change

function fitBoard() {
  const tiles = [...document.querySelectorAll('#board .tile')]
    .filter((t) => t.querySelector('.jl'));
  let px = LABEL_MAX_PX;
  for (const t of tiles) px = Math.min(px, fitsAt(t, px));
  labelPx = px;
  for (const t of tiles) t.querySelector('.jl').style.fontSize = `${px}px`;
}

/** The largest size, from `start` down, at which this tile's label fits: no
 *  word wider than the tile, and nothing pushed out of the top or into the
 *  lamp. */
function fitsAt(tile, start) {
  const jl = tile.querySelector('.jl');
  // The lamp is out of flow, so nothing stops the label and the far-end line
  // under it running into it: they must end above the lamp, not just inside
  // the tile.
  const far = tile.querySelector('.far') || jl;
  const cap = tile.querySelector('.cap');
  for (let px = start; px > LABEL_MIN_PX; px--) {
    jl.style.fontSize = `${px}px`;
    const box = tile.getBoundingClientRect();
    const floor = cap ? cap.getBoundingClientRect().top : box.bottom;
    if (jl.scrollWidth <= jl.clientWidth
        && jl.getBoundingClientRect().top >= box.top
        && far.getBoundingClientRect().bottom <= floor) return px;
  }
  return LABEL_MIN_PX;
}

// A rotation or a resize changes the tile width, so the board is refitted.
window.addEventListener('resize', fitBoard);

// ---- diagnostics (§7.5, Rev 25) ----------------------------------------------

/** A circuit within game/stations and game/trunks (§6.5). Station 24, the
 *  real telephone, is fitted with board 3, when game/stations is 22 (Rev 73). */
function fitted(circuit) {
  const [kind, n] = circuit.split('/');
  const most = num(kind === 'station' ? 'game/stations' : 'game/trunks');
  if (kind === 'station' && +n === PHONE_STATION) return most === null || most === 22;
  return most === null || +n <= most;
}
const diagOn = (target, test) => on(`game/diag/${target}/${test}`);

/** A tap on a command: the echo says which way the toggle goes. */
function toggleDiag(key) {
  const i = key.lastIndexOf('/');
  const target = key.slice(0, i), test = key.slice(i + 1);
  send(`diag/${target}/${test}`, diagOn(target, test) ? 'off' : 'on');
}

document.getElementById('panel-body').addEventListener('click', (e) => {
  const row = e.target.closest('[data-diag]');
  if (row) toggleDiag(row.dataset.diag);
});
document.getElementById('tools').addEventListener('click', (e) => {
  const b = e.target.closest('[data-diag]');
  if (b) toggleDiag(b.dataset.diag);
  // The board sweeps (§7.6; on the deck's keys 5 and 6 until Rev 61).
  const w = e.target.closest('[data-sweep]');
  if (w && get('game/run') !== 'on')
    send('sweep', get('game/sweep') === w.dataset.sweep ? 'off' : w.dataset.sweep);
  // Recording and playback (§7.7, Rev 61).
  const id = e.target.closest('button') && e.target.closest('button').id;
  // Each button stops what it started, and neither starts while the other
  // runs: a playback would be recorded, and recording one is not the point.
  if (id === 'rec-btn') {
    if (recording()) send('record', 'off');
    else if (!playing()) {
      // Tools closes, as it does when a recording is chosen to play: the
      // indicator beside Tools is the sign it runs, and the stop.
      send('record', 'on');
      document.getElementById('tools').hidden = true;
      render();
    }
  }
  if (id === 'play-btn') {
    if (playing()) send('playback', 'stop');
    else if (!recording() && get('game/run') !== 'on') showRecordings();
  }
  // The switchboard's power (§7.8, Rev 65): a toggle, held off until tapped
  // again; not switched off while a game runs.
  if (id === 'power-btn' && !espStale()) {
    if (get('ctl/power_cut') !== 'off') send('power_cut', 'off');
    else if (get('game/run') !== 'on') send('power_cut', 'hold');
  }
});
// Their indicators, beside Tools, are the stops.
document.getElementById('rec-ind').onclick = () => send('record', 'off');
document.getElementById('play-ind').onclick = () => send('playback', 'stop');

/** The recording's name while one runs (audio.md §10.6), else "". */
function recording() {
  const r = get('audio/record');
  return r === 'off' || r === 'failed' ? '' : r;
}
/** Whether a recording is playing back (audio.md §10.7). */
function playing() {
  const p = get('audio/playback');
  return p !== '' && p !== 'missing';
}
/** The local time a recording's name gives, in seconds since the epoch. */
function nameTime(name) {
  const m = /^(\d{4})-(\d\d)-(\d\d)-(\d\d)-(\d\d)-(\d\d)/.exec(name);
  return m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime() / 1000 : NaN;
}
function hms(v) {
  if (!isFinite(v)) return '';
  const n = Math.max(0, Math.floor(v));
  const h = Math.floor(n / 3600), m = Math.floor(n / 60) % 60, s2 = String(n % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s2}` : `${m}:${s2}`;
}
/** audio/recordings: [name, seconds], newest first. */
function recordings() {
  return get('audio/recordings').split('\n').filter(Boolean).map((l) => {
    const [name, secs2] = l.split(' ');
    return [name, +secs2];
  });
}

function showRecordings() {
  const list = recordings();
  document.getElementById('rec-list').innerHTML = list.length
    ? list.map(([n, d]) => `<button data-rec="${esc(n)}">` +
        `${esc(n.slice(0, 10))} ${esc(n.slice(11, 19).replace(/-/g, ':'))}${esc(n.slice(19))}` +
        `<span>${esc(hms(d))}</span></button>`).join('')
    : '<div class="none">No recordings yet.</div>';
  for (const id of ['tools', 'scenes', 'lamps', 'help']) document.getElementById(id).hidden = true;
  document.getElementById('recordings').hidden = false;
}
document.getElementById('rec-list').addEventListener('click', (e) => {
  const b = e.target.closest('[data-rec]');
  if (!b) return;
  send('playback', b.dataset.rec);
  document.getElementById('recordings').hidden = true;
});
// A long press, as on Next Call, shows the lamp key instead (Rev 53).
let toolsTimer = null, toolsLong = false;
const toolsBtn = document.getElementById('tools-btn');
toolsBtn.addEventListener('pointerdown', () => {
  toolsLong = false;
  toolsTimer = setTimeout(() => {
    toolsLong = true;
    document.getElementById('tools').hidden = true;
    document.getElementById('scenes').hidden = true;
    document.getElementById('help').hidden = true;
    document.getElementById('recordings').hidden = true;
    document.getElementById('lamps').hidden = false;
    render();
  }, 500);
});
for (const ev of ['pointerup', 'pointerleave', 'pointercancel'])
  toolsBtn.addEventListener(ev, () => clearTimeout(toolsTimer));
toolsBtn.addEventListener('contextmenu', (e) => e.preventDefault());
toolsBtn.onclick = (e) => {
  e.stopPropagation();
  if (toolsLong) { toolsLong = false; return; }
  const t = document.getElementById('tools');
  t.hidden = !t.hidden;
  document.getElementById('recordings').hidden = true;
  document.getElementById('scenes').hidden = true;
  document.getElementById('lamps').hidden = true;
  document.getElementById('help').hidden = true;
  render();
};

function renderTools() {
  document.getElementById('tools-btn').classList.toggle('sel', !document.getElementById('tools').hidden);
  for (const b of document.querySelectorAll('#tools [data-diag]')) {
    const [target, test] = b.dataset.diag.split('/');
    b.classList.toggle('on', diagOn(target, test));
  }
  const running = get('game/run') === 'on';
  for (const b of document.querySelectorAll('#tools [data-sweep]')) {
    b.classList.toggle('on', get('game/sweep') === b.dataset.sweep);
    b.classList.toggle('dis', running || gameStale());
  }
  const audioDown = gameStale() || audioStale();
  const rec = recording();
  const recBtn = document.getElementById('rec-btn');
  recBtn.classList.toggle('on', !!rec);
  recBtn.classList.toggle('dis', !rec && (playing() || audioDown));
  recBtn.textContent = rec ? 'recording' : get('audio/record') === 'failed' ? 'record (failed)' : 'record';
  document.getElementById('rec-ind').hidden = !rec;

  const play = get('audio/playback');
  const playBtn = document.getElementById('play-btn');
  playBtn.classList.toggle('on', playing());
  playBtn.classList.toggle('dis', !playing() && (running || !!rec || audioDown));
  playBtn.textContent = playing() ? 'playing' : play === 'missing' ? 'play… (missing)' : 'play…';
  document.getElementById('play-ind').hidden = !playing();

  // Lit while the switchboard is powered; dark through a 1s cut too (§7.8).
  const powered = get('ctl/power_cut') === 'off';
  const powerBtn = document.getElementById('power-btn');
  powerBtn.classList.toggle('on', powered);
  powerBtn.classList.toggle('dis', gameStale() || espStale() || (powered && running));
  tickIndicators();
}

// The indicators' times, and the record dot, from one clock, ten times a
// second, so the dot lights on the very tick the count goes up: lit for the
// first half of each second recorded, dark for the second half.
function tickIndicators() {
  const rec = recording();
  if (rec) {
    const t = Date.now() / 1000 + hostOffset - nameTime(rec);
    document.getElementById('rec-time').textContent = hms(t);
    document.querySelector('#rec-ind .dot').classList.toggle('off', t - Math.floor(t) >= 0.5);
  }
  // The time played alone: the bar has no room for the length too, which
  // the list shows.
  if (playing())
    document.getElementById('play-time').textContent = hms((Date.now() - playSince) / 1000);
}
setInterval(tickIndicators, 100);

// ---- help on a long press (§7.1, Rev 54) ---------------------------------------
//
// The pacing buttons and the steppers. A tap still does what it did; holding
// about half a second explains instead, and the click that ends the hold is
// swallowed so it does not also change anything.

const HELP = {
  tutor: ['Tutor', ['A senior operator on the loudspeaker talks the player through each call. Calls start on Next Call only, and nothing times out.',
          'Chosen before Start, she introduces the board and the game opens with one call of each kind. Chosen mid-game, she tutors from the next call. Another pacing stops her at once.',
          'The game returns to Tutor after five minutes stopped.']],
  manual: ['Manual', ['Each call starts on Next Call. Nothing starts one on a schedule, apart from a scene that follows another.']],
  auto: ['Automatic', ['The next call starts a wait after the last one is connected, or ends if sooner, so calls overlap but only one ever waits to be routed.',
         'The wait starts at gap, shrinks by ramp each call connected, down to floor, and is spread by jitter. Now is the wait in use.']],
  listen: ['Listen', ['The next call starts pause seconds after the board is empty, so calls never overlap and every conversation is heard through.',
           'No ramp and no jitter; the automatic settings are left alone.']],
  pause: ['pause', ['Listen: seconds between the board emptying and the next call.'], '0–60 s, steps of 1. Starts at 3.'],
  gap: ['gap', ['Automatic: seconds from one call being connected to the next call, at the start of a game.'], '0–600 s, steps of 5. Starts at 20.'],
  ramp: ['ramp', ['Automatic: seconds taken off the gap for each call connected. 0 keeps the rate constant.'], '0–60 s, steps of 1. Starts at 0.'],
  floor: ['floor', ['Automatic: the shortest the ramp takes the gap. Never above gap.'], '0–600 s, steps of 1. Starts at 5.'],
  jitter: ['jitter', ['Automatic: each wait drawn evenly within this percentage either side of the gap. At 20 s and 50%, every wait is 10–30 s. 0 is a fixed wait.'], '0–100 %, steps of 10. Starts at 0.'],
};

let helpTimer = null, helpSwallow = false;

function showHelp(el) {
  const [title, paras, range] = HELP[el.dataset.help];
  const h = document.getElementById('help');
  h.innerHTML = `<h3>${esc(title)}</h3>` + paras.map((t) => `<p>${esc(t)}</p>`).join('') +
                (range ? `<p class="range">${esc(range)}</p>` : '');
  for (const id of ['tools', 'scenes', 'lamps', 'recordings']) document.getElementById(id).hidden = true;
  h.hidden = false;
  // Under the button, clamped to the window, as a jack's panel is.
  const r = el.getBoundingClientRect(), hr = h.getBoundingClientRect(), pad = 8;
  const left = r.left + r.width / 2 - hr.width / 2;
  h.style.left = `${Math.max(pad, Math.min(left, window.innerWidth - hr.width - pad))}px`;
  h.style.top = `${Math.min(r.bottom + pad, window.innerHeight - hr.height - pad)}px`;
  render();
}

document.addEventListener('pointerdown', (e) => {
  const el = e.target.closest('[data-help]');
  clearTimeout(helpTimer);
  helpSwallow = false;      // a hold released off the button left no click to swallow
  if (!el) return;
  helpTimer = setTimeout(() => { helpSwallow = true; showHelp(el); }, 500);
});
for (const ev of ['pointerup', 'pointercancel'])
  document.addEventListener(ev, () => clearTimeout(helpTimer));
document.addEventListener('pointerout', (e) => {
  if (e.target.closest('[data-help]')) clearTimeout(helpTimer);
});
// Capture, so this runs before the button's own handler and the board's.
document.addEventListener('click', (e) => {
  if (!helpSwallow) return;
  helpSwallow = false;
  e.stopPropagation();
  e.preventDefault();
}, true);
document.addEventListener('contextmenu', (e) => {
  if (e.target.closest('[data-help]')) e.preventDefault();
});

// ---- a chosen next scene (§4.8, Rev 25) ---------------------------------------

function showScenes() {
  const list = document.getElementById('scene-list');
  const queued = get('game/queue');
  const ids = get('game/scenes').split('\n').filter(Boolean).sort();
  list.innerHTML =
    (queued ? `<button data-scene="">clear the choice (${esc(queued)})</button>` : '') +
    ids.map((id) => `<button data-scene="${esc(id)}"${id === queued ? ' class="sel"' : ''}>${esc(id)}</button>`).join('');
  document.getElementById('tools').hidden = true;
  document.getElementById('lamps').hidden = true;
  document.getElementById('help').hidden = true;
  document.getElementById('recordings').hidden = true;
  document.getElementById('scenes').hidden = false;
}
document.getElementById('scene-list').addEventListener('click', (e) => {
  const b = e.target.closest('[data-scene]');
  if (!b) return;
  send('queue', b.dataset.scene);
  document.getElementById('scenes').hidden = true;
});

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
  // Diagnostics (§7.5, Rev 25): commands only on a circuit that is fitted,
  // and only with the controls shown. The row's third element is its test.
  const cmds = circuit && showControls && fitted(circuit);
  const own = kind === 'station' ? 'hook' : 'ring';
  if (circuit) {
    for (const f of (kind === 'station'
                       ? [...(circuit === `station/${PHONE_STATION}` ? ['lifted'] : []),
                          'hook', 'ring', 'peer', 'op', 'play', 'listen', 'fault']
                                        : ['seize', 'ring', 'peer', 'op', 'play', 'tone', 'listen', 'fault']))
      rows.push([f, get(`${circuit}/${f}`) || '—', cmds && f === own ? own : '']);
    if (kind === 'trunk') rows.push(['dialled', get(`${circuit}/dialled`) || '—']);
    const using = [...occupiedSlots()].find(
      (s) => get(`game/call/${s}/trunk`) === circuit);
    rows.push(['in call', using ? get(`game/call/${using}/number`) : '—']);
    if (cmds) for (const t of ['tone', 'voice', 'monitor'])
      rows.push([t, diagOn(circuit, t) ? 'on' : 'off', t]);
  }
  document.getElementById('panel-body').innerHTML =
    `<h3>${esc(kind === 'trunk' ? `Trunk ${n}` : (jackLabel(kind, n) || `Jack ${n}`))}</h3>` +
    rows.map(([k, v, t]) => t
      ? `<div class="cmd${diagOn(circuit, t) ? ' on' : ''}" data-diag="${esc(circuit)}/${t}">` +
        `<span>${esc(k)}</span><b>${esc(String(v))}</b></div>`
      : `<div><span>${esc(k)}</span><b>${esc(String(v))}</b></div>`).join('');
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
  if (!e.target.closest('.sheet') && !e.target.closest('#tools-btn') && !e.target.closest('#next')) {
    document.getElementById('tools').hidden = true;
    document.getElementById('scenes').hidden = true;
    document.getElementById('lamps').hidden = true;
    document.getElementById('recordings').hidden = true;
  }
  if (!e.target.closest('#help')) document.getElementById('help').hidden = true;
  if (!e.target.closest('.tile') && !e.target.closest('#panel')) closePanel();
});
// Escape, for the desktop browser Mark is using to look at this. There is no
// keyboard on the iPad, so it costs nothing there.
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (panelOpen) closePanel();
  for (const id of ['tools', 'scenes', 'lamps', 'help', 'recordings']) document.getElementById(id).hidden = true;
  render();
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
  const f = get('ctl/firmware').split(', ');
  const fw = f.length >= 3 ? [`${f[0].replace('control.md ', '')} ${f[1]}`, f[2].replace('built ', '')]
                           : [get('ctl/firmware'), ''];
  const rows = [
    ['controller', get('ctl/status') || '—', espStale()],
    ['esp beat', age(lastEspBeat), espStale()],
    ['i2c', get('ctl/i2c') || '—', espStale()],
    // §7.1, Rev 27: "control.md Rev 18, 4118077, built 2026-10-01 21:14Z",
    // shown as two rows to fit the column.
    ['firmware', fw[0] || '—', espStale()],
    ['built', fw[1] || '—', espStale()],
    ['audio', get('ctl/audio_status') || '—', audioStale()],
    ['optone', get('audio/optone') || '—', audioStale()],
    ['monitor', get('audio/monitor') || '—', audioStale()],
    ['source', src === 'tap' ? 'tap' : (src ? labelOf(src) : '—'), audioStale()],
    ['game', get('ctl/game_status') || '—', gameStale()],
    ['game beat', age(lastGameBeat), gameStale()],
    // §7.1, Rev 68: tap either row to look again now.
    ['public IP', ipShown(), ipStale(), 'ip'],
    ['checked', ipChecked(), ipStale(), 'ip'],
    ['public trunk', trunkShown(),
     !brokerUp || trunkStale() || get('host/public_trunk') !== 'registered'],
  ];
  document.getElementById('health').innerHTML = rows.map(
    ([k, v, stale, act]) => `<div class="${stale ? 'stale' : ''}${act ? ' tap' : ''}"` +
                            `${act ? ` data-act="${act}"` : ''}><span>${esc(k)}</span>` +
                            `<b>${esc(v)}</b></div>`).join('');
}

// Rev 71: "offline" when the service found no internet, "error" for any other
// failure or a service that has stopped looking, the address otherwise.
function ipShown() {
  const err = get('host/public_ip/error');
  if (err === 'offline') return 'offline';
  const at = num('host/public_ip/checked');
  if (err || (at !== null && hostNow() - at > IP_STALE_S)) return 'error';
  return get('host/public_ip') || '—';
}

function ipChecked() {
  const at = get('host/public_ip/checked');
  if (ipAsked !== null && at === ipAsked && Date.now() - ipAskedAt < 15000) return 'checking…';
  const t = num('host/public_ip/checked');
  if (t === null) return '—';
  const ago = `${secs(hostNow() - t)} ago`;
  return get('host/public_ip/error') ? `failed ${ago}` : ago;
}

document.getElementById('health').addEventListener('click', (e) => {
  if (!e.target.closest('[data-act="ip"]') || !client || !client.connected) return;
  ipAsked = get('host/public_ip/checked');
  ipAskedAt = Date.now();
  client.publish(`${PREFIX}host/public_ip/check/set`, '', { qos: 0 });
  render();
});

function renderTop() {
  document.getElementById('lamp-broker').className = 'lamp ' + (brokerUp ? 'up' : 'down');
  document.getElementById('lamp-game').className =
    'lamp ' + (get('ctl/game_status') === 'online' && !gameStale() ? 'up' : 'down');

  const running = get('game/run') === 'on';
  const pace = get('game/pace');
  const auto = pace === 'auto' || pace === 'listen';   // listen is automatic too (§4.2)
  const disabled = gameStale();

  document.getElementById('start').disabled = disabled || running;
  const stop = document.getElementById('stop');
  stop.disabled = disabled || !running;
  stop.textContent = stopArmed > Date.now() ? 'Stop — again' : 'Stop';
  stop.classList.toggle('armed', stopArmed > Date.now());

  for (const p of ['tutor', 'manual', 'auto', 'listen']) {
    const b = document.getElementById('pace-' + p);
    b.classList.toggle('sel', pace === p);
    b.classList.toggle('dis', disabled);   // not `disabled`: its help (Rev 54) still opens
  }

  const next = document.getElementById('next');
  // Looks disabled rather than being `disabled`, so its long press (§4.8)
  // still works with no game running; the tap handler checks the same thing.
  next.classList.toggle('dis', nextBlocked());
  next.classList.toggle('small', auto);
  const queued = get('game/queue');
  next.innerHTML = 'Next Call' + (queued ? `<small>${esc(queued)}</small>` : '');

  document.getElementById('steppers').style.display = auto ? '' : 'none';
  // Listen has one value of its own, pause, in place of auto's four (Rev 17).
  for (const el of document.querySelectorAll('#steppers .auto-only'))
    el.style.display = pace === 'listen' ? 'none' : '';
  for (const el of document.querySelectorAll('#steppers .listen-only'))
    el.style.display = pace === 'listen' ? '' : 'none';
  for (const f of ['gap', 'ramp', 'floor', 'pause'])
    document.getElementById('v-' + f).textContent = get('game/' + f) || '–';
  const jitter = get('game/jitter');
  document.getElementById('v-jitter').textContent = jitter ? `${jitter}%` : '–';
  document.getElementById('v-gapnow').textContent = get('game/gap_now') || '–';
  const at = num('game/next_at');
  // Nothing scheduled while a game runs is the schedule held up, not idle:
  // auto waits for the latest call to connect, listen for the board to empty.
  document.getElementById('v-countdown').textContent =
    at !== null ? secs(at - hostNow()) : running ? 'waiting' : '–';

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

  document.body.classList.toggle('no-controls', !showControls);
  document.getElementById('controls-toggle').classList.toggle('sel', showControls);
  const runText = get('game/run') === 'on' ? 'Running' : (get('game/run') ? 'Stopped' : '–');
  const paceText = { tutor: 'Tutor', auto: 'Automatic', manual: 'Manual',
                     listen: 'Listen' }[get('game/pace')] || '–';
  const st = document.getElementById('v-state');
  st.textContent = `${runText} · ${paceText}`;
  st.parentElement.classList.toggle('stale', disabled);
}

function render() {
  // Keep an open panel's values live: it reads the same topics as the board.
  if (panelOpen) {
    const [kind, n] = panelOpen.split('/');
    showPanel(kind, +n);
  }
  renderTop();
  renderTools();
  renderBoard();
  renderCalls();
  renderHealth();
  const err = get('game/error');
  const e = document.getElementById('error');
  e.textContent = err;
  e.hidden = !err;
  const log = document.getElementById('log');
  // game_control.md 6.2 publishes the log newest first. It reads better the
  // other way round — down the page, like a terminal — so it is reversed
  // here rather than at the source: anything else subscribing to game/log
  // still gets the order the specification gives.
  const text = get('game/log').split('\n').reverse().join('\n');
  if (log.textContent !== text) {
    // Follow the newest line, unless the reader has scrolled up to look at
    // something — then leave them where they are.
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 24;
    log.textContent = text;
    if (atBottom) log.scrollTop = log.scrollHeight;
  }
  log.classList.toggle('stale', gameStale());
  document.body.classList.toggle('offline', !brokerUp);
}

// ---- taps ------------------------------------------------------------------

document.getElementById('controls-toggle').onclick = () => {
  showControls = !showControls;
  // A stop armed while visible must not fire on the next tap after showing.
  stopArmed = 0;
  try { localStorage.setItem(CONTROLS_KEY, showControls ? 'shown' : 'hidden'); } catch (e) { /* this session only */ }
  render();
};
document.getElementById('start').onclick = () => send('run', 'on');
document.getElementById('stop').onclick = () => {
  // §7.1: a second tap within 3 s, because Stop ends a player's game.
  if (stopArmed > Date.now()) { stopArmed = 0; send('run', 'off'); }
  else { stopArmed = Date.now() + 3000; setTimeout(render, 3100); }
  render();
};
function nextBlocked() {
  return gameStale() || get('game/run') !== 'on' || Date.now() < nextEnabledAt;
}

// A long press, about half a second, lists the scenes (§4.8). The tap that
// ends a long press must not also start a call.
let pressTimer = null, longPressed = false;
const nextBtn = document.getElementById('next');
nextBtn.addEventListener('pointerdown', () => {
  longPressed = false;
  pressTimer = setTimeout(() => { longPressed = true; showScenes(); }, 500);
});
for (const ev of ['pointerup', 'pointerleave', 'pointercancel'])
  nextBtn.addEventListener(ev, () => clearTimeout(pressTimer));
nextBtn.addEventListener('contextmenu', (e) => e.preventDefault());

document.getElementById('next').onclick = () => {
  if (longPressed) { longPressed = false; return; }
  if (nextBlocked()) return;
  // §4.1: QoS 0, never resent on reconnect, and the button disables itself
  // until `started` changes — or 3 s, so a lost tap does not leave it dead.
  send('next', '', 0);
  nextEnabledAt = Date.now() + 3000;
  setTimeout(render, 3100);
  render();
};
for (const p of ['tutor', 'manual', 'auto', 'listen'])          // tutor §4.9, Rev 32
  document.getElementById('pace-' + p).onclick = () => { if (!gameStale()) send('pace', p); };
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
//
// Picking up a new build. From the Home Screen there is no reload button, and
// an app brought back from the background loads nothing, so without help an
// iPad runs the build it first opened with until the app is force-quit.
// Instead: look for a new worker each time the page comes back into view, and
// when one takes over (the worker skips waiting and claims the page), reload
// so this page runs the new build too. The broker holds all the state, so a
// reload loses nothing but the open tile panel.
if ('serviceWorker' in navigator) {
  const hadWorker = !!navigator.serviceWorker.controller;
  let reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    // The first install also claims the page; that is not a new build.
    if (!hadWorker || reloading) return;
    reloading = true;
    location.reload();
  });
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').then((reg) => {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') reg.update().catch(() => {});
      });
    }).catch((e) => {
      // Not fatal: without it the page is an ordinary page.
      console.warn('service worker not registered:', e);
    });
  });
}

connect();
render();
