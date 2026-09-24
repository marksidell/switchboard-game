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
  etc/letsencrypt/renewal-hooks/deploy/nginx:root:root:755

.PHONY: diff install passwd status check-clean

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

## status - what is running and what is served
status:
	@for s in mosquitto nginx certbot.timer; do \
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
