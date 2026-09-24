# Host configuration for portland: the broker, the page's server, the renewal
# hook. mqtt.md 9 and 9.1 are the specification; these are the files as they
# stand on the host, so that a rebuild is a checkout and a `make install`
# rather than an afternoon of reading.
#
#   make diff       what on the host differs from this tree (the useful one)
#   make install    install every file, validate, reload
#   make passwd     rebuild /etc/mosquitto/passwd from the password files
#   make status     services, listeners, certificate
#
# NO SECRET IS IN THIS TREE and none may be added. What is deliberately absent,
# and where it lives instead:
#
#   /etc/mosquitto/passwd     hashed passwords. Rebuilt by `make passwd` from
#                             the files below; never committed, hash or not.
#   /etc/sbgame/mqtt-*.pass   the plaintext passwords, 640 root:<group of the
#                             program that reads it>. On the host only.
#   control/secrets.h         the controller's password, gitignored, and the
#                             source of sbgame-control's entry in passwd.
#   /root/.aws/credentials    the Route 53 key for certbot, [default], 600.
#   /etc/letsencrypt/         the certificate, its key and the ACME account.
#
# So a bare-metal rebuild is: apt install (see README), put the four secrets
# back, `certbot certonly`, `make passwd`, `make install`.

SHELL := /bin/bash
DEST  ?= /
SUDO  ?= sudo

# file-in-this-tree : owner : group : mode
FILES := \
  etc/mosquitto/conf.d/sbgame.conf:root:root:644 \
  etc/mosquitto/acl:root:mosquitto:640 \
  etc/nginx/sites-available/sbgame:root:root:644 \
  etc/letsencrypt/renewal-hooks/deploy/nginx:root:root:755 \
  etc/systemd/system/sbgame.service:root:root:644 \
  etc/sbgame/game.toml:root:root:644

.PHONY: diff install passwd status check-clean sbgame-user sbgame-data sbgame-install sbgame-web sim

## diff - what differs between this tree and the host
diff:
	@rc=0; \
	for spec in $(FILES); do \
	  f=$${spec%%:*}; \
	  if ! $(SUDO) test -e "$(DEST)$$f"; then \
	    echo "MISSING on host: /$$f"; rc=1; \
	  elif ! $(SUDO) diff -q "$$f" "$(DEST)$$f" >/dev/null; then \
	    echo "DIFFERS: /$$f"; $(SUDO) diff -u "$$f" "$(DEST)$$f" | sed 's/^/    /'; rc=1; \
	  else \
	    echo "same:    /$$f"; \
	  fi; \
	  want=$${spec#*:}; own=$${want%%:*}; rest=$${want#*:}; grp=$${rest%%:*}; mode=$${rest#*:}; \
	  if $(SUDO) test -e "$(DEST)$$f"; then \
	    have=$$($(SUDO) stat -c '%U:%G %a' "$(DEST)$$f"); \
	    [ "$$have" = "$$own:$$grp $$mode" ] || { echo "  mode/owner: have $$have, want $$own:$$grp $$mode"; rc=1; }; \
	  fi; \
	done; \
	exit $$rc

## install - put every file in place, validate, then reload
install:
	@for spec in $(FILES); do \
	  f=$${spec%%:*}; want=$${spec#*:}; own=$${want%%:*}; rest=$${want#*:}; \
	  grp=$${rest%%:*}; mode=$${rest#*:}; \
	  $(SUDO) install -D -o "$$own" -g "$$grp" -m "$$mode" "$$f" "$(DEST)$$f" && \
	  echo "installed /$$f  $$own:$$grp $$mode"; \
	done
	@$(SUDO) ln -sfn /etc/nginx/sites-available/sbgame /etc/nginx/sites-enabled/sbgame
	@$(SUDO) rm -f /etc/nginx/sites-enabled/default
	@echo "--- validating before reload, so a bad file cannot take the broker down ---"
	@$(SUDO) nginx -t
	@$(SUDO) systemctl reload nginx
	@$(SUDO) systemctl restart mosquitto
	@sleep 1
	@$(MAKE) --no-print-directory status

## passwd - rebuild the broker password file from the passwords on the host
##
## sbgame-control's password is the one compiled into the firmware, so the
## broker and the board cannot drift apart. The others are in /etc/sbgame.
## mosquitto_passwd -U hashes a plaintext file in place; -b would put every
## password in the process table.
passwd:
	@set -e; umask 077; \
	ctl=$$(sed -n 's/.*MQTT_PASSWORD  *"\([^"]*\)".*/\1/p' ../control/secrets.h); \
	[ -n "$$ctl" ] || { echo "no password in ../control/secrets.h" >&2; exit 1; }; \
	t=$$($(SUDO) mktemp /etc/mosquitto/.passwd.XXXXXX); \
	{ printf 'sbgame-control:%s\n' "$$ctl"; \
	  for u in audio game web; do \
	    printf 'sbgame-%s:%s\n' "$$u" "$$($(SUDO) cat /etc/sbgame/mqtt-$$u.pass)"; \
	  done; } | $(SUDO) tee "$$t" >/dev/null; \
	$(SUDO) mosquitto_passwd -U "$$t"; \
	$(SUDO) install -o root -g mosquitto -m 640 "$$t" /etc/mosquitto/passwd; \
	$(SUDO) rm -f "$$t"; \
	echo "users:"; $(SUDO) cut -d: -f1 /etc/mosquitto/passwd | sed 's/^/  /'

## sbgame-user - the account the game program runs as
##
## A system account with no login and no home: it needs the broker, its
## password file, script.yml and the wavs, and nothing else. The unit's
## StateDirectory makes /var/lib/sbgame for the session log.
sbgame-user:
	@id -u sbgame >/dev/null 2>&1 || { \
	  $(SUDO) useradd --system --no-create-home --shell /usr/sbin/nologin sbgame && \
	  echo "created the sbgame user"; }
	@id sbgame | sed 's/^/  /'
	@echo "the game password file must be readable by it:"
	@$(SUDO) chgrp sbgame /etc/sbgame/mqtt-game.pass 2>/dev/null && \
	  $(SUDO) chmod 640 /etc/sbgame/mqtt-game.pass && \
	  $(SUDO) ls -l /etc/sbgame/mqtt-game.pass | sed 's/^/  /' || \
	  echo "  /etc/sbgame/mqtt-game.pass is not there yet"

## sbgame-install - the game program into /opt/sbgame, as the unit expects
##
## Its own venv, not the developer's: the daemon runs as sbgame and must not
## depend on anything under /home/sidell that ProtectHome could take away. The
## engine and the shared script loader are installed from the checkout, so an
## install is a `git pull` and this target.
REPO := $(shell cd .. && pwd)
sbgame-install: sbgame-user sbgame-data
	@$(SUDO) install -d -m 755 -o root -g root /opt/sbgame
	@test -x /opt/sbgame/venv/bin/python || $(SUDO) python3 -m venv /opt/sbgame/venv
	@$(SUDO) /opt/sbgame/venv/bin/pip -q install --upgrade pip
	@$(SUDO) /opt/sbgame/venv/bin/pip -q install "$(REPO)/engine" "$(REPO)/tts"
	@$(SUDO) /opt/sbgame/venv/bin/sbgame --check -c /etc/sbgame/game.toml
	@$(SUDO) systemctl daemon-reload
	@echo "installed; `systemctl is-enabled sbgame 2>/dev/null || echo not enabled`"

## sbgame-data - the script and the wavs where the daemon can read them
##
## The daemon cannot traverse /home/sidell (0750), so it runs against copies.
## Re-run this after editing script.yml or regenerating wav/, then restart.
sbgame-data:
	@$(SUDO) install -d -m 755 /srv/sbgame
	@$(SUDO) install -m 644 $(HOME)/s/game/script.yml /srv/sbgame/script.yml
	@$(SUDO) rsync -a --delete $(REPO)/wav/ /srv/sbgame/wav/
	@$(SUDO) chmod -R a+rX /srv/sbgame/script.yml /srv/sbgame/wav
	@echo "script.yml and `ls /srv/sbgame/wav | wc -l` wavs installed"

## sbgame-web - the status page into /srv/sbgame/web
##
## app.js carries the broker password, because the page is a browser and has
## nowhere else to put it (mqtt.md 9: the access list is the protection, not
## the password). It is substituted here rather than committed, so the
## repository holds a placeholder and never the password itself.
sbgame-web:
	@test -r /etc/sbgame/mqtt-web.pass || { echo "no /etc/sbgame/mqtt-web.pass"; exit 1; }
	@$(SUDO) install -d -m 755 /srv/sbgame/web
	@$(SUDO) install -d -m 755 /srv/sbgame/web/icons
	@$(SUDO) install -m 644 $(REPO)/engine/web/index.html $(REPO)/engine/web/style.css \
	         $(REPO)/engine/web/mqtt.min.js \
	         $(REPO)/engine/web/manifest.webmanifest /srv/sbgame/web/
	@$(SUDO) install -m 644 $(REPO)/engine/web/icons/*.png /srv/sbgame/web/icons/
	@pw=$$($(SUDO) cat /etc/sbgame/mqtt-web.pass); \
	 sed "s|PAGE_PASSWORD|$$pw|" $(REPO)/engine/web/app.js \
	   | $(SUDO) tee /srv/sbgame/web/app.js >/dev/null
	@$(SUDO) chmod 644 /srv/sbgame/web/app.js
	@build=$$(cat $(REPO)/engine/web/index.html $(REPO)/engine/web/app.js \
	                $(REPO)/engine/web/style.css | md5sum | cut -c1-10); \
	 sed "s|BUILD_ID|$$build|" $(REPO)/engine/web/sw.js \
	   | $(SUDO) tee /srv/sbgame/web/sw.js >/dev/null; \
	 echo "  build $$build"
	@$(SUDO) chmod 644 /srv/sbgame/web/sw.js
	@grep -q PAGE_PASSWORD /srv/sbgame/web/app.js && \
	   { echo "the placeholder is still there"; exit 1; } || true
	@echo "page installed:"; ls -l /srv/sbgame/web | tail -n +2 | sed 's/^/  /'

## sim - stand in for the controller, the audio program and the operator
##
## Until the boards arrive the game program starts, deals a call and stops at
## once: every scene wait fails while ctl/status and ctl/audio_status are down
## (game_control.md 3). This plays both parts on the real broker so the page
## can be used. Foreground, ^C to stop; it is a tool, not a service.
##
##   make -C host sim              hardware only; you are the operator
##   make -C host sim OPERATOR=1   it answers and connects the calls too
OPERATOR ?=
sim:
	@test -r /etc/sbgame/mqtt-audio.pass || { \
	  echo "cannot read /etc/sbgame/mqtt-audio.pass — are you in its group?"; exit 1; }
	/opt/sbgame/venv/bin/sbgame-sim $(if $(OPERATOR),--operator,)

## status - what is running and what is served
status:
	@for s in mosquitto nginx certbot.timer sbgame; do \
	  printf '%-16s %s\n' "$$s" "$$(systemctl is-active $$s)"; \
	done
	@echo "listeners:"
	@$(SUDO) ss -ltnp | grep -E ':(443|1883|9001)\b' | awk '{print "  "$$4}' || true
	@echo "certificate:"
	@openssl s_client -connect 127.0.0.1:443 -servername game.kr3am.org </dev/null 2>/dev/null \
	  | openssl x509 -noout -subject -enddate | sed 's/^/  /' || echo "  not served"

## check-clean - refuse to let a secret into this tree
check-clean:
	@if grep -rqE 'aws_secret_access_key *=|BEGIN [A-Z ]*PRIVATE KEY|\$$6\$$|\$$7\$$' etc iam ; then \
	  echo "secret material found in host/:" >&2; \
	  grep -rlE 'aws_secret_access_key *=|BEGIN [A-Z ]*PRIVATE KEY|\$$6\$$|\$$7\$$' etc iam >&2; \
	  exit 1; \
	else echo "no secret material in etc/ or iam/"; fi
