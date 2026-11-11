#!/bin/sh
# Print the controller's console banner (control.md 9.1).
#
#   control/banner.sh [PORT]        PORT defaults to /dev/ttyUSB0
#
# Opens the port at 115200, waits for the board to boot, sends Enter and
# prints two seconds of what comes back. Needs python3-serial and access to
# the port (the dialout group).
#
# Opening the port resets the board, so the banner is of a board that has just
# started: ticks near zero, the loop timing empty. To watch a board that has
# been running, leave a monitor attached instead of reconnecting each time.
exec python3 - "${1:-/dev/ttyUSB0}" <<'PY'
import serial, sys, time
s = serial.Serial(sys.argv[1], 115200, timeout=0.2)
time.sleep(1.2)                      # let it boot after the open-reset
s.reset_input_buffer()
s.write(b'\n'); s.flush()
t0 = time.time(); buf = b''
while time.time() - t0 < 2: buf += s.read(4096)
s.close()
print(buf.decode('utf-8', 'replace').replace('\r', ''))
PY
