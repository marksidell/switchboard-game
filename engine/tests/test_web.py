"""Checks on the page that do not need a browser.

There is no browser and no iPad here, so how it *looks* is left to someone
looking at it. These are the things that can be checked without one, and each
is a mistake already made once:

  - the JavaScript parses. gjs is SpiderMonkey, so this is a real parse, not
    a bracket count. A typo in app.js otherwise reaches the iPad as a blank
    page with nothing in the log.
  - the page carries the placeholder and never a password.
  - every asset the service worker caches actually exists, or install() caches
    a 404 and the page opens broken when it is next served from cache.
  - the manifest parses and its icons are there.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"


def parses(path: Path) -> bool:
    gjs = shutil.which("gjs")
    src = path.read_text().replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    r = subprocess.run(
        [gjs, "-c", f"try {{ new Function('{src}'); print('ok'); }} "
                    f"catch (e) {{ print('ERR ' + e.message); }}"],
        capture_output=True, text=True, timeout=60)
    out = (r.stdout or r.stderr).strip()
    if not out.startswith("ok"):
        print(f"      {out}")
    return out.startswith("ok")


@pytest.mark.skipif(shutil.which("gjs") is None, reason="needs gjs for a real parse")
@pytest.mark.parametrize("js", ["app.js", "sw.js"])
def test_javascript_parses(js):
    assert parses(WEB / js), f"{js} parses"


def test_placeholders_not_secrets():
    app = (WEB / "app.js").read_text()
    assert "PAGE_PASSWORD" in app, "app.js carries the placeholder, not a password"
    assert "BUILD_ID" in (WEB / "sw.js").read_text(), "sw.js carries the build placeholder"



def test_service_worker_caches_only_what_exists():
    """Every shell entry must exist, or install() caches a 404."""
    sw = (WEB / "sw.js").read_text()
    shell = [p.strip().strip("',") for p in
             sw.split("const SHELL = [")[1].split("];")[0].splitlines() if "'" in p]
    for rel in shell:
        if rel == "/":
            continue
        assert (WEB / rel.lstrip("/")).exists(), f"the worker caches {rel}, which exists"



def test_manifest_and_icons():
    man = json.loads((WEB / "manifest.webmanifest").read_text())
    assert man.get("display") == "standalone", "the manifest asks for standalone"
    for icon in man["icons"]:
        assert (WEB / icon["src"]).exists(), f"manifest icon {icon['src']} exists"
    assert (WEB / "icons/apple-touch-icon.png").exists(), "the apple-touch-icon exists (iOS ignores the manifest for this)"



def test_index_references():
    idx = (WEB / "index.html").read_text()
    for needed in ("manifest.webmanifest", "apple-touch-icon", "mqtt.min.js",
                   "app.js", "style.css"):
        assert needed in idx, f"index.html references {needed}"



def test_hidden_elements_can_hide():
    """An element the page shows and hides with the hidden attribute must not
    be given a display by a rule of its own, or the rule wins and it never
    hides, as the recording indicators once did, unless a [hidden] rule puts
    it back."""
    idx = (WEB / "index.html").read_text()
    css = re.sub(r"/\*.*?\*/", "", (WEB / "style.css").read_text(), flags=re.S)
    rules = re.findall(r"([^{}]+)\{([^}]*)\}", css)
    for tag in re.findall(r"<[a-z]+\b[^>]*\bhidden\b[^>]*>", idx):
        names = ["#" + m for m in re.findall(r'\bid="([^"]+)"', tag)]
        for c in re.findall(r'\bclass="([^"]+)"', tag):
            names += ["." + x for x in c.split()]
        for sel, body in rules:
            if not re.search(r"\bdisplay\s*:\s*(?!none)", body):
                continue
            for one in sel.split(","):
                last = one.split()[-1] if one.split() else ""
                hit = [n for n in names if re.fullmatch(r"[a-z]*" + re.escape(n), last)]
                if hit:
                    assert f"{last}[hidden]" in css, f"{last} sets display and has a [hidden] rule"

