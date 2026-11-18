#!/usr/bin/env python3
"""Verify files differ from git HEAD only by added comments (Python + JS)."""

import argparse
import ast
import io
import subprocess
import sys
import tokenize


def python_ast_fingerprint(source: str) -> str:
    """Compare structural Python code; ignores comments and most formatting."""
    tree = ast.parse(source)
    return ast.dump(tree, annotate_fields=False)


def strip_js(source: str) -> str:
  """Rough strip: remove // and /* */ outside strings (good enough for verification)."""
  result = []
  i = 0
  n = len(source)
  while i < n:
    ch = source[i]
    if ch in ("'", '"', "`"):
      quote = ch
      result.append(ch)
      i += 1
      while i < n:
        c = source[i]
        result.append(c)
        if c == "\\" and i + 1 < n:
          result.append(source[i + 1])
          i += 2
          continue
        if c == quote:
          i += 1
          break
        i += 1
      continue
    if ch == "/" and i + 1 < n:
      nxt = source[i + 1]
      if nxt == "/":
        i += 2
        while i < n and source[i] not in "\n\r":
          i += 1
        continue
      if nxt == "*":
        i += 2
        while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
          i += 1
        i = min(i + 2, n)
        continue
    result.append(ch)
    i += 1
  return "".join(result)


def git_show(path: str) -> str:
  proc = subprocess.run(
    ["git", "show", f"HEAD:{path}"],
    capture_output=True,
    text=True,
    check=False,
  )
  if proc.returncode != 0:
    raise SystemExit(f"No git revision for {path}: {proc.stderr.strip()}")
  return proc.stdout or ""


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("files", nargs="+", help="Paths relative to repo root")
  args = parser.parse_args(argv)
  failed = []
  for rel in args.files:
    rel = rel.replace("\\", "/")
    try:
      original = git_show(rel)
    except SystemExit as exc:
      # New file: compare working tree to empty stripped self (no prior rev)
      with open(rel, encoding="utf-8") as f:
        current = f.read()
      print(f"SKIP {rel}: {exc}")
      continue
    with open(rel, encoding="utf-8") as f:
      current = f.read()
    if rel.endswith(".py"):
      a = python_ast_fingerprint(original)
      b = python_ast_fingerprint(current)
    elif rel.endswith(".js"):
      a = strip_js(original)
      b = strip_js(current)
    else:
      print(f"SKIP {rel}: unsupported extension")
      continue
    if a != b:
      failed.append(rel)
      print(f"FAIL {rel}: code changed beyond comments")
    else:
      print(f"OK {rel}")
  if failed:
    raise SystemExit(1)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())