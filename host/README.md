# Host configuration — portland

The broker, the page's web server and the certificate renewal hook, as they
stand on the Linux host. `mqtt.md` §9 specifies the broker and its access list;
this directory is what was actually installed, so that rebuilding the host is a
checkout and a `make install` rather than an afternoon of reading. The
certificate, the name and nginx's settings have their only description here.

```sh
make diff       what on the host differs from this tree
make install    install every file, validate, reload
make passwd     rebuild /etc/mosquitto/passwd from the passwords on the host
make status     services, listeners, certificate
make check-clean  refuse to let a secret into this tree
```

`make diff` is the one worth running without being asked. Host configuration
drifts — a quick fix at the bench, an edit during commissioning — and nothing
otherwise notices. It exits non-zero when anything differs, in content or in
owner and mode, so it can gate a commit.

## What is here

```text
etc/mosquitto/conf.d/sbgame.conf              two listeners, no anonymous
etc/mosquitto/acl                             who may write what
etc/nginx/sites-available/sbgame              TLS on 443, the page, the /mqtt proxy
etc/letsencrypt/renewal-hooks/deploy/nginx    reload nginx after a renewal
etc/systemd/system/sbgame.service             the game program
etc/systemd/system/sbgame-streamdeck.service  the Stream Deck program
etc/systemd/system/sbaudio.service            the audio program
etc/systemd/system/sbgame-netcheck.service    the public address and the public trunk, for the page
etc/udev/rules.d/70-sbgame-streamdeck.rules   the deck, for the sbgame-deck user
etc/sbgame/game.toml                          the game program's configuration
etc/sbgame/ata-known_hosts                    the trunk 8 ATA's SSH host key, pinned
iam/certbot-route53.json                      the certbot user's policy
```

## What is deliberately not here

No secret is in this tree and none may be added. `make check-clean` enforces
it. What is missing, and where it lives instead:

| | |
| --- | --- |
| `/etc/mosquitto/passwd` | hashed passwords. `make passwd` rebuilds it; never committed, hash or not |
| `/etc/sbgame/mqtt-*.pass` | the plaintext passwords, 640, group = the group of the program that reads it |
| `/etc/sbgame/ata.cred` | the trunk 8 ATA's SSH login (admin): username on line 1, password on line 2; 640, group `sbgame-host` |
| `control/secrets.h` | the controller's password, gitignored, and the source of `sbgame-control`'s entry |
| `/root/.aws/credentials` | the Route 53 key for certbot, `[default]`, 600 |
| `/etc/letsencrypt/` | the certificate, its key, and the ACME account |

## Rebuilding the host from nothing

```sh
sudo apt install mosquitto mosquitto-clients nginx certbot \
                 python3-certbot-dns-route53 dnsutils openssl \
                 libhidapi-libusb0 fonts-dejavu-core lame

# the secrets, by hand:
#   /root/.aws/credentials        [default], 600, the certbot IAM user
#   /etc/sbgame/mqtt-{audio,game,web,deck,host}.pass   640, root:<group>
#   control/secrets.h             from control/secrets.h.example
sudo install -d -m 755 /etc/sbgame /srv/sbgame/web

sudo certbot certonly --dns-route53 -d game.kr3am.org
make passwd
make install
```

`certbot certonly` writes `/etc/letsencrypt/renewal/game.kr3am.org.conf` itself;
it is not kept here, because recreating it by hand rather than by that command
would leave the account and the plugin out of step with it.

## nginx

`etc/nginx/sites-available/sbgame` is enabled, with the distribution's default
site removed; `make install` does both. nginx terminates TLS, serves the page's
files and proxies `/mqtt` to Mosquitto (`mqtt.md` §9).

- `listen 443 ssl http2` is the form Ubuntu 24.04's nginx 1.24 takes. The
  `http2 on` directive is 1.25.1 and later.
- The read and send timeouts are an hour because a game can sit idle between
  calls and the socket must not be dropped for it.
- The master process runs as root and reads the certificate straight from
  `/etc/letsencrypt/live`, so no copy of the key is made.
- The page's files are read by the worker, as `www-data`, from `/srv/sbgame/web`,
  which is world-readable.

## The certificate

Let's Encrypt, for `game.kr3am.org`, by the DNS-01 challenge through Route 53:

```sh
apt install certbot python3-certbot-dns-route53
certbot certonly --dns-route53 -d game.kr3am.org
```

The plugin writes the TXT record `_acme-challenge.game.kr3am.org`, waits for it
to propagate, and removes it after validation. It uses the AWS credentials of the
user certbot runs as, which is root, from `/root/.aws/credentials`. Those belong
to an IAM user whose policy, `iam/certbot-route53.json`, allows only what the
plugin needs: `route53:ListHostedZones` and `route53:GetChange` on everything,
and `route53:ChangeResourceRecordSets` on kr3am.org's hosted zone alone.

The credentials go under `[default]`, in the root account, which has no other
AWS use. The last section below says why.

**Renewal.** The certbot package installs a systemd timer that runs `certbot
renew` twice a day, and a certificate is renewed once it is within 30 days of
expiry. No cron job is written. Renewal needs the host to reach Let's Encrypt and
Route 53, which it does at home. On the road it may not, and does not need to: a
certificate last renewed at home has at least 30 days left.

**Handing it to nginx.** Nothing is copied and the key never leaves
`/etc/letsencrypt/live`. The deploy hook,
`etc/letsencrypt/renewal-hooks/deploy/nginx`, mode 755, which certbot runs after
each successful renewal, only runs `systemctl reload nginx`.

**Reload, not restart.** A reload starts new worker processes with the new
certificate and lets the old ones finish their connections, so no client is
disconnected. This matters because a restart of Mosquitto drops every client: the
ESP32 releases every relay on losing the broker (`mqtt.md` §8.2), and the game
program stops a game in progress (`game_control.md` §2). A reload of nginx touches
neither, since their connections are to Mosquitto, which is not reloaded at all.

## The name

`game.kr3am.org` and `portland.sidell.org` resolve to portland's address, and
`switchboard.sidell.org` to the trunk 8 ATA's. The addresses differ by place, each
fixed by a DHCP reservation: 192.168.0.x at home, 192.168.8.x on the travel router.
The ESP32 uses `portland.sidell.org` to find the broker (`mqtt.md` §9). How the
names reach the clients differs by place:

- **At home**, public DNS: an A record in Route 53, in the kr3am.org zone,
  `game.kr3am.org` to portland's address. OPNsense's resolver returns it as it does
  for portland's existing Route 53 name on the other domain. No entry on OPNsense.
- **On the road**, the GL.iNet Slate 7: NETWORK → DNS → Edit Hosts, one line per
  name, with its address on that LAN. It answers without an upstream, so it works at a venue
  with no internet, and it is not subject to the router's filtering of public
  answers that point at private addresses. If AdGuard Home is turned on in that
  router, the router stops consulting Edit Hosts, and the entry moves to AdGuard
  Home's DNS rewrites.

The iPad and the ESP32 take their DNS from whichever router they are on, so they need
no setting of their own. The certificate's challenge TXT record sits in the same zone during issue
and renewal and does not disturb the A record.

If the host's address ever changes, the Route 53 record and the Edit Hosts line
change together.

A certificate validates offline once issued, so the page works at a venue with no
internet. What must be right is the name, which the travel router answers without
an upstream, and the iPad's clock, which iOS keeps.

## The Stream Deck

`sbgame-streamdeck` drives the Stream Deck+ (`game_control.md` §10). It runs
as its own system user, `sbgame-deck`, which the udev rule gives the deck and
the access list gives the page's rights. Once:

```sh
sudo apt install libhidapi-libusb0 fonts-dejavu-core
sudo sh -c 'umask 027; openssl rand -base64 18 > /etc/sbgame/mqtt-deck.pass'
make passwd                  # adds sbgame-deck to the broker
make install                 # the ACL, the unit, the udev rule
make sbgame-install          # the user, and the program into /opt/sbgame/venv
sudo systemctl enable --now sbgame-streamdeck
journalctl -u sbgame-streamdeck -f
```

It runs with no deck plugged in and picks one up within 2s of it appearing.
If it never does: `lsusb -d 0fd9:` should show `0fd9:0084`, and
`ls -l /dev/bus/usb/*/*` should show that device in group `sbgame-deck`.

## The public address and the public trunk

`sbgame-netcheck` (`mqtt.md` §6.3) asks `checkip.amazonaws.com` for the host's
public address every 5 minutes, and when the page's line is tapped, and
publishes it retained on `sbgame/host/public_ip`. It is not part of the game
program, which makes no network calls during a session; a lookup that fails
shows on the page and nowhere else. It runs as `sbgame-host`, which may write
`sbgame/host/#` only. Once:

```sh
sudo sh -c 'umask 027; openssl rand -base64 18 > /etc/sbgame/mqtt-host.pass'
make passwd                  # adds sbgame-host to the broker
make install                 # the ACL and the unit
make sbgame-install          # the user, and the program into /opt/sbgame/venv
sudo systemctl enable --now sbgame-netcheck
```

`/opt/sbgame/venv/bin/sbgame-netcheck --once` looks once at both and prints them.

The same service looks every 10s at the trunk 8 ATA, `switchboard.sidell.org`,
and publishes its FXS port's registration on `sbgame/host/public_trunk`
(`registered`, `disconnected`, `offline`, `error`). It asks over SSH — `status`,
and the `Port 1:` line of the answer — not through the ATA's web interface,
which keeps one session for the whole device and logged the administrator out of
its pages at every look; SSH does not (2026-10-23). SSH takes the `admin`
account only. `/etc/sbgame/ata.cred` has the username on the first line and the
password on the second:

```sh
sudo sh -c 'umask 027; printf "%s\n%s\n" admin "THE-PASSWORD" > /etc/sbgame/ata.cred'
make sbgame-host-user        # its group and mode
make install                 # the ATA's host key, /etc/sbgame/ata-known_hosts
sudo systemctl restart sbgame-netcheck
```

The ATA's SSH host key is pinned in `etc/sbgame/ata-known_hosts`. A replaced or
factory-reset ATA presents a new one, and the line reads `error` until it is
saved again:

```sh
ssh-keyscan switchboard.sidell.org > etc/sbgame/ata-known_hosts
```

## Two things this host taught us

**Mosquitto cannot serve the page here.** Its WebSockets listener will not bind
a privileged port — libwebsockets creates the socket after Mosquitto drops from
root to the `mosquitto` user — and it advertises HTTP/2 in ALPN without being
able to speak it, so a browser gets nothing. `socket_domain ipv4` and an
ambient `CAP_NET_BIND_SERVICE` with `SecureBits=keep-caps` were both tried and
neither helped. nginx does both jobs; `mqtt.md` §12.17 records it.

**The Route 53 credentials must be `[default]`.** `certbot renew` runs from
`certbot.timer` with an empty environment, so a named profile is invisible to
it: issuance by hand works and every unattended renewal fails. A named profile
needs a systemd drop-in setting `AWS_PROFILE` on `certbot.service`.
