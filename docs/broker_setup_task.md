# Task: the broker on portland — TLS for the page, passwords, access list, certificate

2026-09-24. For Claude Code, running on portland (the Ubuntu 24.04 host). Host setup only. No program source changes, apart from the client credentials in step 3.

## What this sets up

- Mosquitto with two listeners:
  - 1883, plain MQTT, for the controller, `sbaudio` and the game program.
  - 443, WebSockets under TLS. It serves the status page's files over HTTPS and carries the page's MQTT connection over WSS.
- No anonymous clients. A password for each of the four broker users, and an access list that holds the page to the game's own commands.
- A Let's Encrypt certificate for `game.kr3am.org`, issued with the DNS-01 challenge through Route 53. Renewal uses certbot's own timer, and a deploy hook hands each new certificate to Mosquitto.

The specifications are authoritative. This note is a summary and a checklist. Read these sections before you start:

- `mqtt.md` Rev 16: §12.15, §12.16, §9, §9.1, §9.2, §11 (last item)
- `game_control.md` Rev 9: §2, §9 steps 1–4 and 10
- `control.md` §9.1 and `audio.md` §14, for how the controller and `sbaudio` take their broker credentials

## Done by Mark, not by you

Check each one before the step that needs it. If one is missing, stop and ask; don't work around it.

1. **Route 53 A record**: `game.kr3am.org` → portland's fixed address, in the kr3am.org hosted zone. Check with `dig +short game.kr3am.org`.
2. **IAM user for certbot** with the policy in `mqtt.md` §9.1, limited to the kr3am.org zone. Its access key goes in `/root/.aws/credentials` under `[default]`, mode 600, owned by root. Mark puts the key there himself. Don't ask for the key in chat, and don't write it anywhere else.
3. **The Slate 7's Edit Hosts line** for the road (`mqtt.md` §9.2). Not needed for anything in this task.
4. **sudo.** Every step below needs root.

## Step 0: look before changing anything

Record what you find. It goes in the report.

- `mosquitto -h | head -1` for the version. Confirm it's the Ubuntu 2.0.x package.
- `ls /etc/mosquitto/conf.d/` and `cat` every file in it and `/etc/mosquitto/mosquitto.conf`. Note any existing listener, `allow_anonymous`, password file or ACL. If a 9001 WebSockets listener is there from earlier work, it goes away in step 4.
- `sudo ss -ltnp | grep -E ':(443|1883|9001)\b'`. If anything other than Mosquitto holds 443, stop and ask.
- `sudo ufw status`. If ufw is active, note which ports are open.
- **How each client connects now.** Find the username and password each one uses today, if any:
  - the controller: the firmware's broker credentials (`control/control.ino` or its secrets header);
  - `sbaudio`: its systemd unit's `--mqtt-user` and `--mqtt-pass` / `--mqtt-pass-file`;
  - the game program, if it exists yet;
  - anything else that talks to the broker. Check the Mosquitto log for client ids you don't recognise.

## Step 1: packages

```sh
sudo apt install mosquitto mosquitto-clients certbot python3-certbot-dns-route53 dnsutils openssl
```

## Step 2: the certificate

```sh
sudo certbot certonly --dns-route53 -d game.kr3am.org
```

certbot asks for an email address the first time, for expiry notices. Ask Mark which one to use. Accept the terms. Don't put an email address in any file.

Then install the deploy hook exactly as `mqtt.md` §9.1 gives it, at `/etc/letsencrypt/renewal-hooks/deploy/mosquitto`, mode 755. Run it once by hand:

```sh
sudo /etc/letsencrypt/renewal-hooks/deploy/mosquitto
```

The `systemctl kill -s HUP` at the end is harmless if Mosquitto isn't configured for TLS yet. Check the result: `/etc/mosquitto/certs/` is `root:mosquitto` 750, and both files are `root:mosquitto` 640.

Confirm the timer: `systemctl list-timers | grep certbot`.

## Step 3: users and passwords

Four broker users, named as in `mqtt.md` §9: `sbgame-control`, `sbgame-audio`, `sbgame-game`, `sbgame-web`.

- **If a client already uses a different username**, don't rename it on your own. Report it, and ask Mark whether to change the client or the access list. The access list must match what the clients send (`mqtt.md` §9).
- **Passwords.** Keep any password a client already has. Generate the rest, for example with `openssl rand -base64 18`.
- **Where each password lives on the host:**
  - `sbgame-audio` and `sbgame-game`: one file each, `/etc/sbgame/mqtt-audio.pass` and `/etc/sbgame/mqtt-game.pass`, mode 640, owner root, group = the group of the user that runs that program. `sbaudio` reads its file with `--mqtt-pass-file`. Change its unit file to use that option if it passes the password on the command line now.
  - `sbgame-control`: its password is compiled into the firmware. If the firmware has none, or a different one, **don't edit `control/control.ino` as part of this task.** Report what it has. Mark decides, and the firmware change goes through the usual route.
  - `sbgame-web`: goes into the page's `app.js` when the page is written (`game_control.md` §2). Put it in `/etc/sbgame/mqtt-web.pass` for now, same mode, so it can be found then.
- Build `/etc/mosquitto/passwd` with `mosquitto_passwd` (`-c` for the first user only). Set it to `root:mosquitto` 640.
- Write `/etc/mosquitto/acl` exactly as in `mqtt.md` §9, with the same ownership and mode.

Never print a password in your output or the report. Say which files hold them.

## Step 4: the Mosquitto configuration

Do it in two stages, so no client is locked out by surprise.

**Stage A: passwords on, anonymous still allowed.** Write `/etc/mosquitto/conf.d/sbgame.conf` as in `mqtt.md` §9, but with `allow_anonymous true` for now. Remove any earlier listener definitions that clash with it, such as a 9001 WebSockets listener or a second 1883. Remove them from wherever step 0 found them.

Before restarting, put a placeholder page in `http_dir`, so there's something to fetch until `web/` is written:

```sh
sudo install -d -m 755 /srv/sbgame/web
echo '<!doctype html><title>sbgame</title><p>placeholder — status page not yet installed' | sudo tee /srv/sbgame/web/index.html
```

Only do this if `/srv/sbgame/web` is empty. Never overwrite a real `index.html`.

```sh
sudo systemctl restart mosquitto
sudo journalctl -u mosquitto -n 30
tail -n 30 /var/log/mosquitto/mosquitto.log
```

Both listeners should be open, the WebSockets one on 443.

- **If 443 fails to bind:** move to 8443 (`mqtt.md` §9) and report it.
- **If the WebSockets listener doesn't open at all**, check whether the log mentions IPv6. The man page notes that libwebsockets opens IPv6 sockets whenever IPv6 support is compiled in. Adding `socket_domain ipv4` to that listener is the fix to try.
- **If the build turns out to lack WebSockets support**, stop and report it. That's a design question, not a setup one.

Then restart each client, or wait for it to reconnect. Confirm in the Mosquitto log that each one connects **with its username**. 2.0 logs the username on each connect line. A client that still connects anonymously now would be locked out in stage B.

**Stage B: anonymous off.** Change to `allow_anonymous false` and restart. Confirm every client reconnects, and that an anonymous `mosquitto_sub -h localhost -t 'sbgame/#'` is refused.

If ufw is active, allow 443/tcp. Allow 1883/tcp too if the controller's subnet isn't already allowed.

## Step 5: checks

These are `game_control.md` §9 steps 1–4 and 10, as far as they can run from the host.

1. **Listeners.** Both open in the log, as above.
2. **Name and certificate.** From portland, and from another machine on the LAN if you can reach one:
   ```sh
   curl -sS https://game.kr3am.org/ | head -3
   ```
   It returns the placeholder with no certificate error. Also check the certificate and chain:
   ```sh
   openssl s_client -connect game.kr3am.org:443 -servername game.kr3am.org </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -enddate
   ```
3. **WSS carries MQTT.** `mosquitto_sub` 2.0 doesn't speak WebSockets. Check with a short Python script using `paho-mqtt` (`transport="websockets"`, TLS on, port 443, user `sbgame-web`) that subscribes to `sbgame/#` and prints what arrives. Put it in a scratch folder, not in the repository.
4. **The access list.** As `sbgame-web` over WSS, publish `sbgame/station/1/hook/set` `on`. Watch with `mosquitto_sub -v -t 'sbgame/#'` on 1883 as `sbgame-game`: the message never appears. Then publish `sbgame/game/run/set` `off` as `sbgame-web`: it does appear. Use `off`, so a running game program does nothing.
5. **Certificate reload on SIGHUP.** This decides the renewal design (`mqtt.md` §9.1).
   - Start `mosquitto_sub -d -v -t 'sbgame/ctl/#'` on 1883 as `sbgame-game` in the background, logging to a file. It stands in for the controller's connection.
   - Note the served certificate's serial with the `openssl s_client … -serial -enddate` line from `game_control.md` §9 step 10.
   - Run `sudo certbot renew --force-renewal --cert-name game.kr3am.org`. It runs the deploy hook.
   - Note the serial again.
   - **Pass:** the serial changed, and the background subscriber's log shows no disconnect or new CONNACK across the renewal.
   - **Fail:** the old serial is still served. Then SIGHUP doesn't reload the certificate on this build. Put in the fallback from `mqtt.md` §9.1: the hook's last line becomes `touch /run/sbgame-cert-renewed`, and a systemd service and timer at 04:00 restarts Mosquitto only if that file exists, then removes it. Run the forced renewal once more and confirm the flag file appears. Don't force it a third time. Let's Encrypt allows only 5 duplicate certificates per week.

## What not to do

- Don't add a public record, a BIND server or any other DNS on portland. Mark handles DNS (§9.2).
- Don't edit `control/control.ino` or `sbaudio` source. Credentials go in unit files and files under `/etc/sbgame/` only.
- Don't write the status page. The placeholder is the only file in `/srv/sbgame/web`.
- Don't commit anything from `/etc` to the repository.

## Report back

- Step 0's findings: the Mosquitto version, the configuration before, the usernames each client used, and anything unexpected on the broker.
- The final `sbgame.conf`, and the listener port the page ended up on (443 or 8443), and whether `socket_domain ipv4` was needed.
- Which password file each user's password is in, with none of the passwords.
- The controller's credentials situation, and anything the firmware needs changed.
- Each step 5 check, passed or failed. Say plainly which way the SIGHUP reload went, and whether the 04:00 fallback is installed.
- Anything in the specifications that turned out to be wrong on this host, so the next revision of `mqtt.md` can record it.
