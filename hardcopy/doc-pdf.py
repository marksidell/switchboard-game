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
from __future__ import annotations

import pathlib
import re
import sys

from md_pdf import print_pdf, render

HERE = pathlib.Path(__file__).resolve().parent
REV = re.compile(r"^\*?Rev(?:ision)? (\d+(?:\.\d+)*)", re.M)


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    src = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE / f"{src.stem}.pdf"
    source = src.read_text()
    rev = REV.search(source)
    foot = f"{src.name}" + (f", Rev {rev.group(1)}" if rev else "")
    body = render(source)
    # The title block: everything before the first heading.
    head, sep, rest = body.partition("<h1>")
    body = f'<header class="title">{head}</header>{sep}{rest}'
    css = (HERE / "doc-pdf.css").read_text()
    css += "@page { @bottom-left { content: %s; } }\n" % _css_string(foot)
    print_pdf(body, css, src.stem, src.parent, out)
    print(out)


def _css_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


if __name__ == "__main__":
    main()
