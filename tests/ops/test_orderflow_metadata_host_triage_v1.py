"""Synthetic-only security and fail-closed tests for Order Flow host metadata triage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import textwrap

SCRIPT = Path(__file__).resolve().parents[2] / 'ops/forensics/qnty_orderflow_host_triage_v1.sh'


def _stub(tmp_path: Path, *, journal_exit: int = 0) -> dict:
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    systemctl = bindir / 'systemctl'
    systemctl.write_text(textwrap.dedent('''\
        #!/usr/bin/env python3
        print('ActiveState=active')
        print('SubState=running')
        print('Result=success')
        print('LastTriggerUSec=Thu 2026-10-22 14:05:00 UTC')
        print('MainPID=PLEASE_DO_NOT_ECHO_SECRET_CANARY')
    '''))
    systemctl.chmod(0o755)
    journalctl = bindir / 'journalctl'
    journalctl.write_text(textwrap.dedent(f'''\
        #!/usr/bin/env python3
        import json
        import sys
        if {journal_exit}:
            print('error contains SECRET_CANARY', file=sys.stderr)
            sys.exit({journal_exit})
        print(json.dumps({{'__REALTIME_TIMESTAMP':'1790258400000000', 'PRIORITY':'3', '_SYSTEMD_INVOCATION_ID':'a'*32, 'MESSAGE':'SECRET_CANARY private journal content'}}))
        print(json.dumps({{'__REALTIME_TIMESTAMP':'1790258401000000', 'PRIORITY':'6', '_SYSTEMD_INVOCATION_ID':'a'*32, 'MESSAGE':'some more sensitive output'}}))
        print('not-json-secret-SECRET_CANARY')
    '''))
    journalctl.chmod(0o755)
    return {**os.environ, 'PATH':str(bindir)+os.pathsep+os.environ.get('PATH','')}


def test_metadata_only_no_messages_or_untrusted_unit_fields(tmp_path):
    proc = subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True,
                          env=_stub(tmp_path), timeout=15)
    assert proc.returncode == 0, proc.stderr
    assert 'SECRET_CANARY' not in proc.stdout
    assert 'private journal content' not in proc.stdout
    data = json.loads(proc.stdout)
    assert data['host_identity_verified'] is False
    assert data['collector_user_identity_verified'] is False
    assert data['timer_state']['fields']['ActiveState'] == 'active'
    assert 'MainPID' not in data['timer_state']['fields']
    for window in data['windows']:
        assert window['entry_count'] == 2
        assert window['malformed_entry_count'] == 1
        assert window['unique_structured_invocations'] == 1
        assert window['by_priority'] == {'3':1, '6':1}


def test_no_fabricated_success_on_journal_failure(tmp_path):
    proc = subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True,
                          env=_stub(tmp_path, journal_exit=1), timeout=15)
    assert proc.returncode == 2
    assert 'SECRET_CANARY' not in proc.stdout
    assert 'SECRET_CANARY' not in proc.stderr
    data = json.loads(proc.stdout)
    assert all(w['journal_query_ok'] is False and w['entry_count'] is None
               for w in data['windows'])
