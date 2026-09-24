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

**The page shows echoes, never its own requests** (§7.2). A tap publishes a
`/set` and changes nothing on screen; the display moves when the game
program's state topic moves. There is deliberately no local model of the game
here — only a map of retained topic values and a render that reads it.
