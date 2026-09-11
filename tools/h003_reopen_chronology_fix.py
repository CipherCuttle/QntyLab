from __future__ import annotations

from pathlib import Path


path = Path("qntylab/research_ledger.py")
text = path.read_text(encoding="utf-8")
old = '''            if not later_decision:
                issues.append(f"reopen does not target latest decision: {event['event_id']}")
                continue
        if variant["status"] not in TERMINAL_DECISION_STATUSES:
'''
new = '''            if later_decision:
                # This reopen has already been consumed to authorize the later
                # decision. Preserve that later decision on replay; an older
                # reopen must never reactivate a subsequently terminal variant.
                continue
            issues.append(f"reopen does not target latest decision: {event['event_id']}")
            continue
        if variant["status"] not in TERMINAL_DECISION_STATUSES:
'''
if new not in text:
    if text.count(old) != 1:
        raise SystemExit(f"expected one chronology repair anchor, found {text.count(old)}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
