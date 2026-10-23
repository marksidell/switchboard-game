# Host configuration — portland

The broker, the page's web server and the certificate renewal hook, as they
stand on the Linux host. `mqtt.md` §9 and §9.1 are the specification; this
directory is what was actually installed, so that rebuilding the host is a
checkout and a `make install` rather than an afternoon of reading.

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
etc/sbgame/ata-cert.pem                       the trunk 8 ATA's certificate, pinned
iam/certbot-route53.json                      the certbot user's policy
```

## What is deliberately not here

No secret is in this tree and none may be added. `make check-clean` enforces
it. What is missing, and where it lives instead:

| | |
| --- | --- |
| `/etc/mosquitto/passwd` | hashed passwords. `make passwd` rebuilds it; never committed, hash or not |
| `/etc/sbgame/mqtt-*.pass` | the plaintext passwords, 640, group = the group of the program that reads it |
| `/etc/sbgame/ata.cred` | the trunk 8 ATA's web login: username on line 1, password on line 2; 640, group `sbgame-host` |
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

## The Stream Deck

`sbgame-streamdeck` drives the Stream Deck+ (`game_control.md` §7.4). It runs
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
(`registered`, `disconnected`, `offline`, `error`). It logs in to the ATA's web
interface with `/etc/sbgame/ata.cred`, the username on the first line and the
password on the second. Use the ATA's `viewer` account, not `admin`: the ATA
keeps one session per account, so an `admin` login every 10s logs the admin out
of the web page. The viewer is off by default — System Settings → Security
Settings → Web Access → Enable Viewer Level Web Access — and needed a reboot of
the ATA to take effect (2026-10-23):

```sh
sudo sh -c 'umask 027; printf "%s\n%s\n" viewer "THE-PASSWORD" > /etc/sbgame/ata.cred'
make sbgame-host-user        # its group and mode
make install                 # the ATA's certificate, /etc/sbgame/ata-cert.pem
sudo systemctl restart sbgame-netcheck
```

The ATA's certificate is pinned: it is issued to the ATA's MAC address, not its
name, so the certificate itself in `etc/sbgame/ata-cert.pem` is what is
trusted. A replaced or factory-reset ATA may present a new one, and the line
reads `error` until it is saved again:

```sh
echo | openssl s_client -connect switchboard.sidell.org:443 2>/dev/null \
  | openssl x509 > etc/sbgame/ata-cert.pem
```

## Two things this host taught us

**Mosquitto cannot serve the page here.** Its WebSockets listener will not bind
a privileged port — libwebsockets creates the socket after Mosquitto drops from
root to the `mosquitto` user — and it advertises HTTP/2 in ALPN without being
able to speak it, so a browser gets nothing. `socket_domain ipv4` and an
ambient `CAP_NET_BIND_SERVICE` with `SecureBits=keep-caps` were both tried and
neither helped. nginx does both jobs; `mqtt.md` §1.17 records it.

**The Route 53 credentials must be `[default]`.** `certbot renew` runs from
`certbot.timer` with an empty environment, so a named profile is invisible to
it: issuance by hand works and every unattended renewal fails. A named profile
needs a systemd drop-in setting `AWS_PROFILE` on `certbot.service`.
