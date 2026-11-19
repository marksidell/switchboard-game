#!/usr/bin/env python3
"""README.md as a PDF, with its images in it.

    python3 hardcopy/readme-pdf.py [OUTPUT.pdf]

Writes hardcopy/README.pdf by default. A line reading <!-- pagebreak --> in the
README starts a new page here and is invisible on GitHub. The automatic rules
(headings stay with their text, images and tables do not split) and the look are
in readme-pdf.css. Footnotes ([^1]) print as endnotes at the end, as on GitHub.
The foot of each page names the last commit of README.md and its date, with
"edited" after it when the file differs from that commit; commit the README
before rendering for a clean stamp. A video GitHub plays in place (a
<video> of a user-attachments URL) prints as a link to it.
Needs python3-markdown-it, python3-mdit-py-plugins and Google Chrome 131 or later."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

from md_pdf import print_pdf, render

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
VIDEO = re.compile(r'<video src="(https://github\.com/user-attachments/assets/[^"]+)"[^>]*></video>')


def stamp() -> str:
    """'Commit 3864141 17-Nov-2026', from the last commit that changed README.md."""
    git = ["git", "-C", str(ROOT)]
    line = subprocess.run(
        git + ["log", "-1", "--format=%h %cd", "--date=format:%d-%b-%Y", "--", "README.md"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    edited = subprocess.run(git + ["diff", "--quiet", "HEAD", "--", "README.md"]).returncode != 0
    return f"Commit {line}" + (" (edited)" if edited else "")


def main() -> None:
    out = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "README.pdf"
    source = VIDEO.sub(r'<a href="\1">Play the video (on GitHub)</a>', (ROOT / "README.md").read_text())
    body = render(source)
    css = (HERE / "readme-pdf.css").read_text()
    css += '@page { @bottom-left { content: "%s"; } }\n' % stamp()
    print_pdf(body, css, "The Switchboard Game", ROOT, out)
    print(out)


if __name__ == "__main__":
    main()
