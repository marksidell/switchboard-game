"""Checks on the page that do not need a browser.

There is no browser and no iPad here, so how it *looks* is unverifiable and
Mark is the test for that. These are the things that can be checked without
one, and each is a mistake already made once:

  - the JavaScript parses. gjs is SpiderMonkey, so this is a real parse, not
    a bracket count. A typo in app.js otherwise reaches the iPad as a blank
    page with nothing in the log.
  - the page carries the placeholder and never a password.
  - every asset the service worker caches actually exists, or install() caches
    a 404 and the page opens broken when it is next served from cache.
  - the manifest parses and its icons are there.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
failures = 0


def check(ok, what):
    global failures
    print(f"  {what:<56} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


def parses(path: Path) -> bool:
    gjs = shutil.which("gjs")
    if not gjs:
        print("  (no gjs; skipping the parse check)")
        return True
    src = path.read_text().replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    r = subprocess.run(
        [gjs, "-c", f"try {{ new Function('{src}'); print('ok'); }} "
                    f"catch (e) {{ print('ERR ' + e.message); }}"],
        capture_output=True, text=True, timeout=60)
    out = (r.stdout or r.stderr).strip()
    if not out.startswith("ok"):
        print(f"      {out}")
    return out.startswith("ok")


def main() -> int:
    print("the page")
    for js in ("app.js", "sw.js"):
        check(parses(WEB / js), f"{js} parses")

    app = (WEB / "app.js").read_text()
    check("PAGE_PASSWORD" in app, "app.js carries the placeholder, not a password")
    check("BUILD_ID" in (WEB / "sw.js").read_text(),
          "sw.js carries the build placeholder")

    # Every shell entry must exist, or install() caches a 404.
    sw = (WEB / "sw.js").read_text()
    shell = [p.strip().strip("',") for p in
             sw.split("const SHELL = [")[1].split("];")[0].splitlines() if "'" in p]
    for rel in shell:
        if rel == "/":
            continue
        check((WEB / rel.lstrip("/")).exists(), f"the worker caches {rel}, which exists")

    man = json.loads((WEB / "manifest.webmanifest").read_text())
    check(man.get("display") == "standalone", "the manifest asks for standalone")
    for icon in man["icons"]:
        check((WEB / icon["src"]).exists(), f"manifest icon {icon['src']} exists")
    check((WEB / "icons/apple-touch-icon.png").exists(),
          "the apple-touch-icon exists (iOS ignores the manifest for this)")

    idx = (WEB / "index.html").read_text()
    for needed in ("manifest.webmanifest", "apple-touch-icon", "mqtt.min.js",
                   "app.js", "style.css"):
        check(needed in idx, f"index.html references {needed}")

    print("\n" + ("FAILURES" if failures else "the page passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
