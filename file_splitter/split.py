"""One-shot splitter. Deleted after the packages are in place."""

import ast
import os
import re
import shutil
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from packages import PACKAGES


def span(node):
    start = node.lineno
    if getattr(node, "decorator_list", None):
        start = node.decorator_list[0].lineno
    return start, node.end_lineno


def used_names(source):
    tree = ast.parse(source)
    found = set()

    class Walk(ast.NodeVisitor):
        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                found.add(node.id)
            self.generic_visit(node)

    Walk().visit(tree)
    return found


def import_lines(tree, needed):
    lines = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            kept = [alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
                    for alias in node.names
                    if (alias.asname or alias.name.split(".")[0]) in needed]
            if kept:
                lines.append("import " + ", ".join(kept))
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            kept = []
            for alias in node.names:
                bound = alias.asname or alias.name
                if bound in needed:
                    kept.append(alias.name if alias.asname is None else f"{alias.name} as {alias.asname}")
            if kept:
                lines.append(f"from {module} import " + ", ".join(kept))
    return lines


def slice_text(lines, start, end):
    return "\n".join(lines[start - 1:end]).rstrip() + "\n"


def dedented_methods(lines, nodes):
    chunks = [slice_text(lines, *span(node)).rstrip() for node in nodes]
    body = "\n\n".join(textwrap.dedent(chunk) for chunk in chunks).rstrip() + "\n"
    return textwrap.indent(body, "    ")


def render_module(spec, module, lines, lookup, owners, external):
    pieces = []
    defined_here = set()
    if module.get("assigns"):
        for name in module["assigns"]:
            node = lookup["assigns"][name]
            pieces.append(slice_text(lines, *span(node)).rstrip())
            defined_here.add(name)
    if module.get("classes"):
        for name in module["classes"]:
            node = lookup["classes"][name]
            pieces.append(slice_text(lines, *span(node)).rstrip())
            defined_here.add(name)
    if module.get("funcs"):
        for name in module["funcs"]:
            node = lookup["funcs"][name]
            pieces.append(slice_text(lines, *span(node)).rstrip())
            defined_here.add(name)
    if module.get("methods"):
        nodes = [lookup["methods"][name] for name in module["methods"]]
        method_body = dedented_methods(lines, nodes)
        if spec.get("replace_runtime"):
            method_body = re.sub(r"\bruntime\b", "self.runtime", method_body)
        pieces.append(f"class {module['class_name']}:\n{method_body}".rstrip())
    source_for_names = "\n\n".join(pieces) + "\n"
    needed = used_names(source_for_names)
    header = import_lines(lookup["tree"], needed)
    for name in sorted(needed):
        if name in defined_here or name in module.get("methods", []):
            continue
        owner = owners.get(name)
        if owner and owner != module["name"]:
            stem = owner[:-3] if owner.endswith(".py") else owner
            header.append(f"from {spec['package']}.{stem} import {name}")
        elif name in external:
            header.append(f"from {external[name]} import {name}")
    body = source_for_names
    if module.get("methods") and spec.get("replace_runtime"):
        body = source_for_names
    text = ("\n".join(header) + ("\n\n" if header else "") + body).rstrip() + "\n"
    return text


def build_lookup(tree):
    lookup = {"tree": tree, "funcs": {}, "assigns": {}, "classes": {}, "methods": {}}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lookup["funcs"][node.name] = node
            for inner in ast.walk(node):
                if isinstance(inner, ast.ClassDef):
                    for item in inner.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            lookup["methods"][item.name] = item
        elif isinstance(node, ast.ClassDef):
            lookup["classes"][node.name] = node
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lookup["methods"][item.name] = item
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    lookup["assigns"][target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            lookup["assigns"][node.target.id] = node
    return lookup


def owners_for(spec):
    owners = {}
    for module in spec["modules"]:
        for key in ("funcs", "assigns", "classes"):
            for name in module.get(key, []):
                owners[name] = module["name"]
    return owners


def write_package(spec):
    path = ROOT / spec["file"]
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    lookup = build_lookup(tree)
    owners = owners_for(spec)
    external = spec.get("external", {})
    staging = path.with_name(path.stem + "__next")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    written = {}
    for module in spec["modules"]:
        text = render_module(spec, module, lines, lookup, owners, external)
        ast.parse(text)
        target = staging / module["name"]
        target.write_text(text, encoding="utf-8", newline="\n")
        written[module["name"]] = text.count("\n")
    init = staging / "__init__.py"
    init.write_text(spec["init"], encoding="utf-8", newline="\n")
    ast.parse(spec["init"])
    written["__init__.py"] = spec["init"].count("\n")
    return staging, written


def split_tests(path, fixture_names):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    lookup = build_lookup(tree)
    test_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Tests"))
    methods = [item for item in test_class.body if isinstance(item, ast.FunctionDef)]
    groups = []
    current = []
    current_lines = 0
    for method in methods:
        start, end = span(method)
        size = end - start + 1
        if current and current_lines + size > 100:
            groups.append(current)
            current = []
            current_lines = 0
        current.append(method)
        current_lines += size
    if current:
        groups.append(current)
    package = path.stem
    qual = f"tests.{package}"
    staging = path.with_name(package + "__next")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    owners = {}
    modules = []
    if fixture_names:
        modules.append({"name": "fixtures.py", "funcs": [name for name in fixture_names if name in lookup["funcs"]], "classes": [name for name in fixture_names if name in lookup["classes"]]})
        for name in fixture_names:
            owners[name] = "fixtures.py"
    part_classes = []
    for index, group in enumerate(groups, start=1):
        name = f"part_{index}.py"
        class_name = f"Part{index}"
        modules.append({"name": name, "class_name": class_name, "methods": [method.name for method in group]})
        part_classes.append((name, class_name))
    spec = {"package": qual, "file": str(path.relative_to(ROOT)).replace("\\", "/"), "modules": modules, "external": {}, "replace_runtime": False}
    # methods live on the test class, so point lookup methods at that class
    written = {}
    for module in modules:
        text = render_module(spec, module, lines, lookup, owners, {})
        ast.parse(text)
        (staging / module["name"]).write_text(text, encoding="utf-8", newline="\n")
        written[module["name"]] = text.count("\n")
    imports = "\n".join(f"from {qual}.{name[:-3]} import {class_name}" for name, class_name in part_classes)
    bases = ", ".join(class_name for _, class_name in part_classes)
    init = f"import unittest\n\n{imports}\n\n\nclass {test_class.name}({bases}, unittest.TestCase):\n    pass\n"
    ast.parse(init)
    (staging / "__init__.py").write_text(init, encoding="utf-8", newline="\n")
    written["__init__.py"] = init.count("\n")
    return staging, written


def commit(staging, original):
    original.unlink()
    destination = original.with_suffix("")
    if destination.exists():
        raise SystemExit(f"Refusing to replace {destination}")
    staging.rename(destination)


def main():
    staged = []
    too_long = []
    for spec in PACKAGES:
        staging, written = write_package(spec)
        staged.append((staging, ROOT / spec["file"], written, spec["file"]))
        for name, count in written.items():
            if count > 150:
                too_long.append((spec["file"], name, count))
    test_jobs = [
        (ROOT / "tests/test_dialer_session.py", []),
        (ROOT / "tests/test_transcript_storage.py", ["prospect", "FakeSupabaseClient"]),
    ]
    for path, fixtures in test_jobs:
        staging, written = split_tests(path, fixtures)
        staged.append((staging, path, written, str(path.relative_to(ROOT))))
        for name, count in written.items():
            if count > 150:
                too_long.append((str(path.relative_to(ROOT)), name, count))
    for _staging, _original, written, label in staged:
        print(label)
        for name, count in written.items():
            mark = " OVER" if count > 150 else ""
            print(f"  {count:4} {name}{mark}")
    if too_long:
        for staging, _original, _written, _label in staged:
            shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit("files still over 150 lines")
    for staging, original, _written, _label in staged:
        commit(staging, original)


if __name__ == "__main__":
    main()
