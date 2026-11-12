"""Markdown to PDF through headless Chrome, for doc-pdf.py and readme-pdf.py.

Needs python3-markdown-it, python3-mdit-py-plugins and Google Chrome 131 or later."""
from __future__ import annotations

import html
import pathlib
import re
import subprocess
import tempfile

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

BREAK = re.compile(r"<!--\s*pagebreak\s*-->", re.I)


def render(source: str) -> str:
    """Markdown as HTML: tables, raw HTML, footnotes as endnotes, and a line
    reading <!-- pagebreak --> as a page break."""
    source = BREAK.sub('<div style="break-after: page"></div>', source)
    md = MarkdownIt("commonmark", {"html": True}).enable("table").use(footnote_plugin)
    # A plain superscript number, not the plugin's "[1]".
    md.add_render_rule("footnote_caption", lambda self, tokens, idx, *_: str(tokens[idx].meta["id"] + 1))
    return md.render(source)


def print_pdf(body: str, css: str, title: str, base: pathlib.Path, out: pathlib.Path) -> None:
    """Write `body` as a PDF at `out`, relative links resolved from `base`."""
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<base href="{base.as_uri()}/"><title>{html.escape(title)}</title>'
        f"<style>{css}</style></head><body>{body}</body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        page_file = pathlib.Path(tmp) / "page.html"
        page_file.write_text(page)
        subprocess.run(
            [
                "google-chrome", "--headless", "--disable-gpu",
                f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer",
                "--virtual-time-budget=20000", f"--print-to-pdf={out}", page_file.as_uri(),
            ],
            check=True, capture_output=True,
        )
