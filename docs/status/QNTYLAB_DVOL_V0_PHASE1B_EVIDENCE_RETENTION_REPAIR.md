# QNTYLAB DVOL V0 Phase 1B evidence-retention repair

- Repair date UTC: `2026-08-03`
- PR: `#4`
- Initial PR head: `0fdfbaf666f81d6b87b0f998ef15a5d7eb0a931e`
- Historical smoke code commit: `0700c0d54c06a4e43f0fa801cb83c20de0d5f87e`
- Historical receipt commit: `0fdfbaf666f81d6b87b0f998ef15a5d7eb0a931e`
- Historical artifact root: `/tmp/qntylab-dvol-v0-phase1b-20260803T023243Z`
- Historical manifest SHA-256: `aeb42fcab71b05f98b8fc472a9ec9de8145b9dd48b8850c90498253107a624b0`
- Historical artifact verification: `PASS` (paths, byte counts, hashes, flags, and no `weeks` directory)
- Historical acknowledgement availability: `ABSENT`
- Historical mismatch classification: `ACK_UNRESOLVED`

The historical receipt remains unchanged. The confirmed defect was retention
after classification rather than before it. Future message bytes are timestamped,
hashed, retained, and indexed before strict parsing and classification.

Official Deribit documentation says subscription results list subscribed
channels but does not establish result ordering. The repair uses exact semantic
set equality with cardinality, string-type, and duplicate checks while retaining
both orders as diagnostics. Source probes are independent; aggregate success is
complete only with all sources valid, partial only for acknowledged Deribit
notification absence with both Binance sources valid, and otherwise blocked.

Offline fake-transport coverage includes strict acknowledgement parsing,
retention of blocked bytes, independent Binance probes, and artifact
truthfulness. `network_attempts_during_task=0`. This remains non-authority: no
rerun, network access, scheduled collection, primary observation, analysis, or
QNTY authority was created.
