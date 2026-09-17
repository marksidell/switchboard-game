#!/bin/sh
# Ask the ring board for its banner. NOTE: opening the port resets the board,
# so ticks will read near zero. To watch a board that has been running, leave
# a monitor attached instead of reconnecting each time.
exec python3 - "$@" <<'PY'
import serial, time
s = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.2)
time.sleep(1.2)                      # let it boot after the open-reset
s.reset_input_buffer()
s.write(b'\n'); s.flush()
t0 = time.time(); buf = b''
while time.time() - t0 < 2: buf += s.read(4096)
s.close()
print(buf.decode('utf-8', 'replace').replace('\r', ''))
PY
