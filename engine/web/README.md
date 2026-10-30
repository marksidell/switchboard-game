# The status page

game_control.md §2 and §7. Served by nginx from `/srv/sbgame/web`; its MQTT
socket is proxied to Mosquitto on the path `/mqtt` (mqtt.md §9).

```text
index.html    the page; the vendored MQTT.js version is noted at the top
app.js        everything the page does
style.css
mqtt.min.js   MQTT.js 5.10.1, the browser build from the npm package's dist/
```

Install with `make -C host sbgame-web`.

## The password

`app.js` in this directory carries `PAGE_PASSWORD`, a placeholder. The install
target substitutes the real one from `/etc/sbgame/mqtt-web.pass`, so the
repository never holds it and the installed copy always matches the broker.

The password is readable by anyone who loads the page, and that is accepted:
the access list is the protection, not the password (mqtt.md §9). `sbgame-web`
can read everything under `sbgame/` and write only `sbgame/game/+/set`, so a
page that tried to close a relay would see nothing happen.

## Two things that are easy to get wrong

**`location = /mqtt` in the nginx site is an exact match on purpose.** A prefix
match also catches `/mqtt.min.js` and proxies the page's own copy of MQTT.js to
Mosquitto, which is not a web server. The symptom is a 502 for that one file
and a page that loads with its library missing.

**The page shows echoes, never its own requests** (§11.2). A tap publishes a
`/set` and changes nothing on screen; the display moves when the game
program's state topic moves. There is deliberately no local model of the game
here — only a map of retained topic values and a render that reads it.

## Installed as an app

`manifest.webmanifest` and `sw.js` make it installable: Add to Home Screen on
the iPad and it opens without Safari's bars, landscape, on the dark background
(game_control.md §7.3). iOS reads the `apple-*` tags rather than the manifest
for that, so both are in `index.html` and have to agree.

The service worker is not really about being offline. The page is served from
the same host the game program runs on, so if nginx is unreachable the game is
too. It is there to make the page installable, to open it from cache when the
iPad has been asleep, and to survive nginx restarting or the host being
mid-reboot. Stale-while-revalidate: the cached copy is served at once and a
fresh one fetched behind it, so a deploy is picked up on the next load.

Two things in the nginx site exist only for this, and both are easy to get
wrong:

- **`location = /sw.js` sets `Cache-Control: no-cache`.** A cached service
  worker is the one file that can outlive a deploy indefinitely, because the
  browser re-fetches it and a stale copy keeps serving the old shell.
- **The manifest's type comes from a `location`, not a `types { }` block.**
  A `types` block inside a server *replaces* the inherited MIME map rather
  than adding to it. With one there, every other file goes out as
  `application/octet-stream`: the page does not render, and the worker is
  refused outright, because a worker must be served with a JavaScript type.

`icons/` is drawn by a script rather than by hand: a grid of jacks with two
joined by a cord and one calling, which is the board in miniature.
