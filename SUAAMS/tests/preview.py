"""Render a template to a static HTML file and screenshot it with headless Chrome.

A design change is very hard to review from markup alone -- the whole point of
the light-theme redesign was how the page *looks*, and none of the other
checks in tests/ exercise that. This renders a page against the real Flask
app with a synthetic session, rewrites the /static/... href to a relative path
so it works over file://, and drives Chrome to capture it.

The template and its context come from the CONTEXTS table in render_check.py,
so anything registered there can be previewed by name.

Usage:
    python tests/preview.py admin/dashboard.html
    python tests/preview.py admin/dashboard.html --out dash.png --size 1440x980
    python tests/preview.py --list
    python tests/preview.py admin/dashboard.html --no-css    # check unstyled
"""

import pathlib
import re
import shutil
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from render_check import CONTEXTS, render  # noqa: E402

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser():
    for path in CHROME_CANDIDATES:
        if pathlib.Path(path).exists():
            return path
    return shutil.which("chrome") or shutil.which("msedge")


def main(argv):
    if "--list" in argv:
        for name in CONTEXTS:
            print(name)
        return 0

    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    template = args[0]

    if template not in CONTEXTS:
        print(f"No context registered for {template!r}.")
        print("Add it to the CONTEXTS table in tests/render_check.py first.")
        return 2

    out = ROOT / "_preview.png"
    size = (1440, 980)
    for i, a in enumerate(argv):
        if a == "--out" and i + 1 < len(argv):
            out = ROOT / argv[i + 1]
        if a == "--size" and i + 1 < len(argv):
            w, _, h = argv[i + 1].partition("x")
            size = (int(w), int(h))

    html = render(template, CONTEXTS[template])

    # url_for() emits an absolute /static/... path, which under file://
    # resolves to the filesystem root and silently fails to load -- the page
    # then renders completely unstyled, which looks like a CSS bug rather
    # than a path bug. Rewrite to relative so it resolves next to this file.
    if "--no-css" not in argv:
        html = html.replace("/static/", "static/")

    preview = ROOT / "_preview.html"
    preview.write_text(html, encoding="utf-8")

    browser = find_browser()
    if not browser:
        print("No Chrome or Edge found; wrote _preview.html only. Open it manually.")
        return 0

    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={size[0]},{size[1]}",
        f"--screenshot={out.resolve()}",
        preview.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    noise = [
        line
        for line in result.stderr.splitlines()
        if "error" in line.lower()
        and "extension" not in line.lower()
        and "install" not in line.lower()
    ]
    for line in noise[:5]:
        print("  chrome:", line)

    if out.exists():
        print(f"wrote {out.name} ({out.stat().st_size} bytes) from {template}")
        return 0
    print("screenshot failed")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
