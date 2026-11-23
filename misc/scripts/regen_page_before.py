"""Regenerate misc/docs/page-before.html from the same partials as send_app_page."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.vocabulary import vocabulary_json

STATIC = ROOT / "frontend"
parts = (
    STATIC / "shell.html",
    STATIC / "features" / "dialer.html",
    STATIC / "features" / "ai-dialer-agent.html",
    STATIC / "features" / "session-summary-dialog.html",
<<<<<<< HEAD:misc/scripts/regen_page_before.py
=======
    STATIC / "features" / "performance.html",
    STATIC / "features" / "pipeline.html",
    STATIC / "features" / "workflow.html",
>>>>>>> 1f6194cd2ae87ec7fff49dab3cbd173c490ead53:scripts/regen_page_before.py
    STATIC / "features" / "prospects.html",
    STATIC / "features" / "settings.html",
    STATIC / "shell-end.html",
)
body = b"".join(p.read_bytes() for p in parts)
script = (
    b'<script type="application/json" id="vocabulary">'
    + vocabulary_json().encode("utf-8")
    + b"</script>"
)
body = body.replace(b"</head>", script + b"</head>", 1)
out = ROOT / "misc" / "docs" / "page-before.html"
out.write_bytes(body)
print(f"wrote {out} ({len(body)} bytes)")
