#!/usr/bin/env python3
"""README.md as a PDF, with its images in it.

    python3 hardcopy/readme-pdf.py [OUTPUT.pdf]

Writes hardcopy/README.pdf by default. A line reading <!-- pagebreak --> in the
README starts a new page here and is invisible on GitHub. The automatic rules
(headings stay with their text, images and tables do not split) and the look are
in readme-pdf.css. Footnotes ([^1]) print as endnotes at the end, as on GitHub.
Needs python3-markdown-it, python3-mdit-py-plugins and Google Chrome 131 or later."""
from __future__ import annotations

import pathlib
import sys

from md_pdf import print_pdf, render

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def main() -> None:
    out = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "README.pdf"
    body = render((ROOT / "README.md").read_text())
    print_pdf(body, (HERE / "readme-pdf.css").read_text(), "The Switchboard Game", ROOT, out)
    print(out)


if __name__ == "__main__":
    main()
