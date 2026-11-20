#!/usr/bin/env python3
"""List static JS/CSS not reachable from main.js or HTML partials."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STATIC = ROOT / "frontend"
PARTIALS = (
    STATIC / "shell.html",
    STATIC / "features" / "dialer.html",
    STATIC / "features" / "ai-dialer-agent.html",
    STATIC / "features" / "session-summary-dialog.html",
    STATIC / "features" / "performance.html",
    STATIC / "features" / "pipeline.html",
    STATIC / "features" / "workflow.html",
    STATIC / "features" / "prospects.html",
    STATIC / "features" / "settings.html",
    STATIC / "shell-end.html",
)
IMPORT_FROM = re.compile(
    r"""(?:import|export)\s+(?!type\b)(?:[\s\S]*?\sfrom\s+)?["'](\.[^"']+)["']""",
)
LINKED_ASSET = re.compile(
    r"""<(?:link|script)\b[^>]*?(?:href|src)=["']([^"']+)["']""",
    re.I,
)


def resolve_specifier(source, specifier):
    raw = (source.parent / specifier).resolve()
    if raw.suffix:
        return raw
    for suffix in (".js", ".mjs"):
        candidate = raw.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return raw


def reachable_from(entry):
    seen = set()
    stack = [entry.resolve()]
    while stack:
        path = stack.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        for match in IMPORT_FROM.finditer(text):
            target = resolve_specifier(path, match.group(1))
            if target.is_file():
                stack.append(target)
    return seen


def linked_css():
    html = "".join(p.read_text(encoding="utf-8") for p in PARTIALS if p.is_file())
    assets = set()
    for match in LINKED_ASSET.finditer(html):
        url = match.group(1)
        if url.startswith(("http://", "https://", "//", "data:", "#")):
            continue
        relative = url.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if relative.startswith("static/"):
            relative = relative[len("static/") :]
        assets.add((STATIC / relative).resolve())
    return assets


def main():
    live_js = reachable_from(STATIC / "main.js")
    all_js = set(STATIC.rglob("*.js"))
    orphan_js = sorted(all_js - live_js)

    live_css = linked_css()
    all_css = set(STATIC.rglob("*.css"))
    orphan_css = sorted(all_css - live_css)

    print("=== Orphan JS (not imported from main.js) ===")
    for path in orphan_js:
        print(path.relative_to(ROOT))
    print(f"total: {len(orphan_js)} / {len(all_js)}")

    print("\n=== Orphan CSS (not linked from page partials) ===")
    for path in orphan_css:
        print(path.relative_to(ROOT))
    print(f"total: {len(orphan_css)} / {len(all_css)}")


if __name__ == "__main__":
    main()