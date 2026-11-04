#!/usr/bin/env python3
"""README.md as a PDF, with its images in it.

    python3 hardcopy/readme-pdf.py [OUTPUT.pdf]

Writes hardcopy/README.pdf by default. A line reading <!-- pagebreak --> in the
README starts a new page here and is invisible on GitHub. The automatic rules
(headings stay with their text, images and tables do not split) and the look are
in readme-pdf.css. Footnotes ([^1]) print as endnotes at the end, as on GitHub.
Needs python3-markdown-it, python3-mdit-py-plugins and Google Chrome 131 or later."""
import pathlib, re, subprocess, sys, tempfile

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
BREAK = re.compile(r"<!--\s*pagebreak\s*-->", re.I)


def main() -> None:
    out = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "README.pdf"
    source = (ROOT / "README.md").read_text()
    source = BREAK.sub('<div style="break-after: page"></div>', source)
    md = MarkdownIt("commonmark", {"html": True}).enable("table").use(footnote_plugin)
    # A plain superscript number, not the plugin's "[1]".
    md.add_render_rule("footnote_caption", lambda self, tokens, idx, *_: str(tokens[idx].meta["id"] + 1))
    body = md.render(source)
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<base href="{ROOT.as_uri()}/"><title>The Switchboard Game</title>'
        f'<style>{(HERE / "readme-pdf.css").read_text()}</style></head>'
        f"<body>{body}</body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        html = pathlib.Path(tmp) / "README.html"
        html.write_text(page)
        subprocess.run(
            [
                "google-chrome", "--headless", "--disable-gpu",
                f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer",
                "--virtual-time-budget=20000", f"--print-to-pdf={out}", html.as_uri(),
            ],
            check=True, capture_output=True,
        )
    print(out)


if __name__ == "__main__":
    main()
