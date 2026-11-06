#!/usr/bin/env python3
"""One-off: build static/features/ai-dialer-agent.html from dialer.html with prefixed ids."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "static" / "features" / "dialer.html").read_text(encoding="utf-8")
start = src.index('<section id="dialerTabPanel"')
aside_end = src.rfind("</aside>", start)
if aside_end < 0:
    raise SystemExit("gen_ai_dialer_partial: missing </aside>")
close = src.find("</section>", aside_end)
if close < 0:
    raise SystemExit("gen_ai_dialer_partial: missing closing </section>")
block = src[start : close + len("</section>")]

block = re.sub(
    r'<section id="dialerTabPanel"[^>]*>',
    '<section id="aiDialerAgentTabPanel" class="dialer-run-panel dialer-workspace dashboard-tab-panel" '
    'role="tabpanel" aria-labelledby="aiDialerAgentTabButton aiDialerAgent-liveTitle" tabindex="0" hidden>',
    block,
    count=1,
)


def prefix_id(match: re.Match) -> str:
    val = match.group(1)
    if val == "aiDialerAgentTabPanel":
        return match.group(0)
    if val.startswith("aiDialerAgent-"):
        return match.group(0)
    return f'id="aiDialerAgent-{val}"'


block = re.sub(r'id="([^"]+)"', prefix_id, block)

# References to #ids in aria-* must match prefixed element ids.
block = block.replace('aria-labelledby="dialerTimezoneLabel"', 'aria-labelledby="aiDialerAgent-dialerTimezoneLabel"')
block = block.replace('aria-controls="dialerTimezoneList"', 'aria-controls="aiDialerAgent-dialerTimezoneList"')
block = block.replace('aria-labelledby="crmStatusLabel"', 'aria-labelledby="aiDialerAgent-crmStatusLabel"')
block = block.replace('aria-labelledby="callMonitorTitle"', 'aria-labelledby="aiDialerAgent-callMonitorTitle"')
block = block.replace('aria-controls="prospectNotesPanel"', 'aria-controls="aiDialerAgent-prospectNotesPanel"')
block = block.replace('aria-labelledby="prospectNotesTitle"', 'aria-labelledby="aiDialerAgent-prospectNotesTitle"')
block = block.replace('aria-labelledby="sendInfoNotesTitle"', 'aria-labelledby="aiDialerAgent-sendInfoNotesTitle"')

out = ROOT / "static" / "features" / "ai-dialer-agent.html"
out.write_text(block + "\n", encoding="utf-8")
print(out, "bytes", out.stat().st_size)
