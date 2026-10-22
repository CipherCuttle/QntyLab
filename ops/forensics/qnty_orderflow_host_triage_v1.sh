#!/usr/bin/env bash
# QntyLab Order Flow V1: strictly metadata-only, read-only host triage.
# Does not read MESSAGE fields, provider data, evidence releases or credentials.
set -euo pipefail
umask 077
export TZ=UTC LC_ALL=C

python3 - <<'PY'
import collections
import datetime as dt
import json
import os
import subprocess
import sys

SERVICE = 'order-flow-v1-prospective-record.service'
TIMER = 'order-flow-v1-prospective-record.timer'
WINDOWS = (
    ('sep24_publication_gap', '2026-09-24 09:00:00', '2026-09-25 02:00:00'),
    ('oct21_22_recent', '2026-10-21 22:00:00', '2026-10-22 16:00:00'),
)
ALLOWED_UNIT_PROPERTIES = {
    'ActiveState', 'SubState', 'UnitFileState', 'Result', 'LastTriggerUSec',
    'NextElapseUSecRealtime', 'ExecMainStatus', 'ExecMainCode',
}
ALLOWED_STATUS = {'active','inactive','failed','activating','deactivating','reloading','dead','running','waiting','elapsed','loaded','enabled','disabled','static','unknown','success','exit-code','signal','timeout','start-limit-hit'}


def run_safely(argv):
    try:
        p = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=45, env={**os.environ, 'TZ': 'UTC', 'LC_ALL': 'C'})
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return -1, ''


def unit_properties(unit):
    args = ['systemctl', '--user', 'show', unit, '--no-pager', '--property=' + ','.join(sorted(ALLOWED_UNIT_PROPERTIES))]
    rc, output = run_safely(args)
    parsed = {}
    if rc == 0:
        for line in output.splitlines():
            k, sep, v = line.partition('=')
            if not sep or k not in ALLOWED_UNIT_PROPERTIES:
                continue
            if k in ('ActiveState','SubState','UnitFileState','Result','ExecMainCode'):
                parsed[k] = v if v in ALLOWED_STATUS else 'UNRECOGNIZED_OR_UNAVAILABLE'
            elif k == 'ExecMainStatus':
                parsed[k] = int(v) if v.isdigit() and len(v) < 6 else None
            else:
                # Systemd timestamps only; strict allowlist, never a verbatim arbitrary value.
                parsed[k] = v if len(v) < 80 and all(c.isascii() and (c.isalnum() or c in ' :.-+/') for c in v) else None
    return {'query_ok': rc == 0, 'fields': parsed}


def journal_summary(name, start, end):
    argv = ['journalctl', '--user', '-u', SERVICE, '--no-pager', '-o', 'json', '--since', start, '--until', end]
    rc, stdout = run_safely(argv)
    by_hour = collections.Counter()
    by_priority = collections.Counter()
    invocation_ids = set()
    malformed = 0
    accepted = 0
    for line in stdout.splitlines() if rc == 0 else []:
        try:
            e = json.loads(line)
            if not isinstance(e, dict):
                raise ValueError('nonobject journal row')
            timestamp = e.get('__REALTIME_TIMESTAMP')
            if not isinstance(timestamp, str) or not timestamp.isdecimal():
                raise ValueError('missing timestamp')
            when = dt.datetime.fromtimestamp(int(timestamp)/1e6, dt.timezone.utc)
            hour = when.strftime('%Y-%m-%dT%H:00Z')
            by_hour[hour] += 1
            prio = e.get('PRIORITY')
            if prio in tuple(str(x) for x in range(8)):
                by_priority[str(prio)] += 1
            invocation = e.get('_SYSTEMD_INVOCATION_ID')
            if isinstance(invocation, str) and len(invocation) == 32 and all(c in '0123456789abcdef' for c in invocation.lower()):
                invocation_ids.add(invocation)
            accepted += 1
        except (ValueError, OverflowError, OSError, TypeError):
            malformed += 1
    return {
        'name':name, 'since_utc':start.replace(' ', 'T')+'Z', 'until_utc':end.replace(' ', 'T')+'Z',
        'journal_query_ok':rc == 0, 'entry_count':accepted if rc == 0 else None,
        'malformed_entry_count':malformed if rc == 0 else None,
        'unique_structured_invocations':len(invocation_ids) if rc == 0 else None,
        'by_priority':dict(sorted(by_priority.items())),
        'entries_by_hour':dict(sorted(by_hour.items())),
        # No MESSAGE, invocation IDs, usernames, env, paths, machine-id or arbitrary stderr printed.
    }


result = {
    'schema':'qntylab-orderflow-metadata-only-host-triage-v1',
    'authority':'READ_ONLY_OPERATIONAL_METADATA_NO_SCIENTIFIC_OUTCOME',
    'host_identity_verified':False,
    'collector_user_identity_verified':False,
    'service':SERVICE,
    'timer':TIMER,
    'service_state':unit_properties(SERVICE),
    'timer_state':unit_properties(TIMER),
    'windows':[journal_summary(*w) for w in WINDOWS],
    'interpretation':'METADATA_ONLY; no proof of exact scheduler invocations, complete origin coverage, legitimate backfill, chain validity or economic edge. Compare privately with trusted host and release anchors.',
    'remediation':'NONE; do not restart, backfill, issue due runs, modify timer, access outcomes or trade.',
}
print(json.dumps(result,sort_keys=True,indent=2))
if not result['service_state']['query_ok'] or not result['timer_state']['query_ok'] or any(not x['journal_query_ok'] for x in result['windows']):
    # Query failures still emit bounded JSON and signal operator that the evidence is incomplete.
    sys.exit(2)
PY
