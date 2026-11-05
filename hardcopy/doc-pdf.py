#!/usr/bin/env python3
"""A specification in docs/ as a PDF, for the binder.

    python3 hardcopy/doc-pdf.py docs/game_control.md [OUTPUT.pdf]

Writes hardcopy/<name>.pdf by default. The document's own title lines (the bold
paragraphs before the first heading) open the first page, and every page's foot
carries the file name, its revision and the page number. The look is in
doc-pdf.css; the automatic rules (headings stay with their text, tables and code
blocks do not split) are the same as readme-pdf.css's. A line reading
<!-- pagebreak --> starts a new page, as in the README.
Needs python3-markdown-it, python3-mdit-py-plugins and Google Chrome 131 or later."""
import html, pathlib, re, subprocess, sys, tempfile

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
BREAK = re.compile(r"<!--\s*pagebreak\s*-->", re.I)
REV = re.compile(r"^\*?Rev(?:ision)? (\d+(?:\.\d+)*)", re.M)


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    src = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE / f"{src.stem}.pdf"
    source = src.read_text()
    rev = REV.search(source)
    foot = f"{src.name}" + (f", Rev {rev.group(1)}" if rev else "")
    source = BREAK.sub('<div style="break-after: page"></div>', source)
    md = MarkdownIt("commonmark", {"html": True}).enable("table").use(footnote_plugin)
    md.add_render_rule("footnote_caption", lambda self, tokens, idx, *_: str(tokens[idx].meta["id"] + 1))
    body = md.render(source)
    # The title block: everything before the first heading.
    head, sep, rest = body.partition("<h1>")
    body = f'<header class="title">{head}</header>{sep}{rest}'
    css = (HERE / "doc-pdf.css").read_text()
    css += "@page { @bottom-left { content: %s; } }\n" % _css_string(foot)
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<base href="{src.parent.as_uri()}/"><title>{html.escape(src.stem)}</title>'
        f"<style>{css}</style></head><body>{body}</body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        page_file = pathlib.Path(tmp) / f"{src.stem}.html"
        page_file.write_text(page)
        subprocess.run(
            [
                "google-chrome", "--headless", "--disable-gpu",
                f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer",
                "--virtual-time-budget=20000", f"--print-to-pdf={out}", page_file.as_uri(),
            ],
            check=True, capture_output=True,
        )
    print(out)


def _css_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


if __name__ == "__main__":
    main()
