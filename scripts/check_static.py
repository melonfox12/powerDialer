#!/usr/bin/env python3
"""Check that static JS imports resolve, named exports exist, DOM ids exist, and linked assets exist."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
PARTIALS = (
    STATIC / "app-shell" / "chrome.html",
    STATIC / "app-shell" / "dialer.html",
    STATIC / "app-shell" / "metrics.html",
    STATIC / "app-shell" / "dialogs.html",
)

IMPORT_FROM = re.compile(
    r"""(?:import|export)\s+(?!type\b)(?:[\s\S]*?\sfrom\s+)?["'](\.[^"']+)["']""",
)
NAMED_IMPORT = re.compile(
    r"""import\s*\{([^}]+)\}\s*from\s*["'](\.[^"']+)["']""",
)
NAMED_REEXPORT = re.compile(
    r"""export\s*\{([^}]+)\}\s*from\s*["'](\.[^"']+)["']""",
)
EXPORT_FUNCTION = re.compile(r"""export\s+(?:async\s+)?function\s+(\w+)""")
EXPORT_DECL = re.compile(r"""export\s+(?:const|let|var|class)\s+(\w+)""")
EXPORT_LIST = re.compile(r"""export\s*\{([^}]+)\}(?!\s*from)""")
DOM_ID = re.compile(
    r"""(?:\bbyId|getElementById)\(\s*["']([^"']+)["']\s*\)|querySelector(?:All)?\(\s*["']#([\w-]+)"""
)
HTML_ID = re.compile(r"""\bid=["']([^"']+)["']""")
LINKED_ASSET = re.compile(
    r"""<(?:link|script)\b[^>]*?(?:href|src)=["']([^"']+)["']""",
    re.I,
)
ASSIGNED_ID = re.compile(r"""\.id\s*=\s*["']([^"']+)["']""")


def resolve_specifier(source, specifier):
    raw = (source.parent / specifier).resolve()
    if raw.suffix:
        return raw
    for suffix in (".js", ".mjs"):
        candidate = raw.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return raw


def specifier_names(block):
    names = []
    for part in block.split(","):
        part = part.strip()
        if not part:
            continue
        if " as " in part:
            original, exported = (piece.strip() for piece in part.split(" as ", 1))
        else:
            original = exported = part
        names.append((original, exported))
    return names


def local_exports(text):
    names = set(EXPORT_FUNCTION.findall(text))
    names.update(EXPORT_DECL.findall(text))
    for block in EXPORT_LIST.findall(text):
        for _original, exported in specifier_names(block):
            names.add(exported)
    return names


def main():
    problems = []
    js_files = []
    for folder in (STATIC / "js", STATIC / "_core", STATIC / "features"):
        if folder.is_dir():
            js_files.extend(folder.rglob("*.js"))
    for name in ("core.js", "main.js"):
        candidate = STATIC / name
        if candidate.is_file():
            js_files.append(candidate)
    js_files = sorted(set(js_files))
    texts = {path: path.read_text(encoding="utf-8") for path in js_files}
    export_cache = {}

    def exported(path, stack):
        if path in export_cache:
            return export_cache[path]
        if path in stack:
            problems.append(f"import cycle involving {path.relative_to(ROOT)}")
            return set()
        if not path.is_file():
            return set()
        text = texts.get(path)
        if text is None:
            text = path.read_text(encoding="utf-8")
            texts[path] = text
        stack.add(path)
        names = local_exports(text)
        for block, specifier in NAMED_REEXPORT.findall(text):
            target = resolve_specifier(path, specifier)
            available = exported(target, stack)
            for original, alias in specifier_names(block):
                if original not in available:
                    problems.append(
                        f"{path.relative_to(ROOT)} re-exports {original}, which {target.relative_to(ROOT)} does not export"
                    )
                names.add(alias)
        stack.remove(path)
        export_cache[path] = names
        return names

    for path, text in texts.items():
        for match in IMPORT_FROM.finditer(text):
            target = resolve_specifier(path, match.group(1))
            if not target.is_file():
                problems.append(f"{path.relative_to(ROOT)} imports missing {match.group(1)}")
        for block, specifier in NAMED_IMPORT.findall(text):
            target = resolve_specifier(path, specifier)
            if not target.is_file():
                continue
            available = exported(target, set())
            for original, _alias in specifier_names(block):
                if original not in available:
                    problems.append(
                        f"{path.relative_to(ROOT)} imports {original} from {specifier}, but it is not exported"
                    )

    html = "".join(path.read_text(encoding="utf-8") for path in PARTIALS if path.is_file())
    html_ids = set(HTML_ID.findall(html))
    html_ids.add("vocabulary")  # injected by web.send_app_page before </head>
    for text in texts.values():
        html_ids.update(ASSIGNED_ID.findall(text))
    for path, text in texts.items():
        for match in DOM_ID.finditer(text):
            element_id = match.group(1) or match.group(2)
            if element_id not in html_ids:
                problems.append(f"{path.relative_to(ROOT)} uses missing DOM id #{element_id}")

    for match in LINKED_ASSET.finditer(html):
        url = match.group(1)
        if url.startswith(("http://", "https://", "//", "data:", "#", "mailto:")):
            continue
        relative = url.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if relative.startswith("static/"):
            relative = relative[len("static/"):]
        asset = STATIC / relative
        if not asset.is_file():
            problems.append(f"linked asset missing: {url}")

    if problems:
        print("\n".join(problems))
        return 1
    print(f"checked {len(js_files)} scripts, {len(html_ids)} DOM ids")
    return 0


if __name__ == "__main__":
    sys.exit(main())
