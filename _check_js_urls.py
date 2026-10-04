import re
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent / "static" / "js"
base = "http://127.0.0.1:8000/js/"
seen = set()
bad = []


def visit(rel):
    if rel in seen:
        return
    seen.add(rel)
    try:
        with urllib.request.urlopen(base + rel, timeout=5) as resp:
            text = resp.read().decode("utf-8")
            code = resp.status
    except Exception as exc:
        bad.append((rel, str(exc)))
        return
    if code != 200:
        bad.append((rel, code))
        return
    here = Path(rel).parent
    for match in re.findall(r"""from ["'](\.[^"']+)["']""", text):
        target = (here / match).as_posix()
        parts = []
        for part in target.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        visit("/".join(parts))


visit("main.js")
print("checked", len(seen))
print("bad", bad or "none")
