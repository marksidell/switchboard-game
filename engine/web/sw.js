/* Service worker for the status page.
 *
 * What it is actually for here. The page is served from the same host the
 * game program runs on, so "offline" in the usual sense barely applies: if
 * nginx is unreachable the game is unreachable too. Its real jobs are
 *
 *   - to make the page installable, so it opens from the Home Screen without
 *     Safari's bars (game_control.md §7.3);
 *   - to open instantly from cache rather than four requests deep, which
 *     matters when the iPad has been asleep and Mark wants the board *now*;
 *   - to survive nginx restarting, a certificate reload, or the host being
 *     mid-reboot while the iPad is already awake.
 *
 * Strategy: stale-while-revalidate for the shell. Serve the cached copy at
 * once and fetch a fresh one in the background, so a deploy is picked up on
 * the next load rather than needing the cache version bumped by hand. Bump
 * VERSION anyway when a file changes, which drops the old cache outright.
 *
 * What it must not touch: the MQTT socket. WebSockets do not go through
 * fetch, so /mqtt never reaches this worker — but anything that is not a
 * same-origin GET is passed straight through regardless, so a future change
 * cannot accidentally intercept a command.
 */
'use strict';

// Stamped at install with a hash of the shell (`make -C host sbgame-web`).
// A new build means a new cache name, so activate drops the old one and the
// first load after a deploy is fresh rather than stale-then-fresh. Without
// this, every change needs two reloads to appear, which during development
// looks exactly like the change not working.
const VERSION = 'sbgame-BUILD_ID';
const SHELL = [
  '/',
  '/index.html',
  '/app.js',
  '/style.css',
  '/mqtt.min.js',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(VERSION)
      // Not addAll: one missing file would reject the whole install and leave
      // the page with no worker at all.
      .then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname === '/mqtt') return;            // belt and braces; see above

  e.respondWith(
    caches.open(VERSION).then(async (cache) => {
      const hit = await cache.match(req, { ignoreSearch: true });
      const fresh = fetch(req)
        .then((res) => {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        })
        .catch(() => null);
      // Cached copy at once if there is one; otherwise wait for the network.
      // A navigation with neither falls back to the cached shell, so a reload
      // while the host is rebooting still opens the page.
      return hit || (await fresh) || (await cache.match('/index.html')) ||
             new Response('offline', { status: 503, statusText: 'offline' });
    })
  );
});
