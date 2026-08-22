# Independent hostile implementation review

The phase used one broad independent review and, after repairing its
Critical/High findings, exactly one targeted rereview. The reviewer was
read-only. No external model/provider request, real secret read, or real claim
was made by either review.

## Broad review

Counts: Critical 1, High 1, Medium 2, Low 0.

- C-01: the launch identity was evidence-only. Caller-controlled
  `QNTYLAB_ROOT`, an unverified DSH_HOME package tree, a trusted caller-made
  preflight object, and no required replacement-contract digest could
  substitute all enforcement.
- H-01: the raw providers resolved bare `codex` and `claude` from ambient PATH
  instead of the executable paths fingerprinted by preflight.
- M-01: claim uniqueness is scoped to the caller-selected remote/ref/local
  tuple. This must be bound by the future authorization envelope.
- M-02: the recorded qualification is a curated evidence artifact rather than
  a byte-for-byte copy of the runner's camelCase stdout, and zero real-I/O
  counters are safety assertions supported by the loopback/disposable setup.

C-01 and H-01 were repaired. The launcher now requires and dynamically checks
the replacement contract, runtime, executables, canonical policy, mirrored
QntyLab gate packages, and critical DSH runtime package trees immediately
before spawn. It derives QntyLab root internally and repeats preflight rather
than trusting the supplied object. Both native providers receive a restricted
PATH that resolves exactly to the fingerprinted executables; the actual DSH
`resolveExecutable` seam is exercised by the native stubs.

## Single targeted rereview

The targeted rereview marked H-01 PASS and the core C-01 repairs sound. It then
found H-RR-01: the offline-only seam still accepted an arbitrary temporary
patch under a loopback/fake-sentinel condition. Counts at that rereview were
Critical 0, High 1.

H-RR-01 was repaired after the rereview. The launcher now accepts only the
exact committed `stub/offline-stub.patch.yml`; that full stub-only profile,
the stub provider, and the native stub executable are covered by the final
launch-policy digest. The canonical production profile remains fixed. A
focused malicious-patch test rejects an arbitrary patch, and the final actual
full-profile double-rereview scenario passes with native counts 2/2 and exact
preflighted executable matches.

No second rereview was performed because the authorization permits at most
one. Final open counts after the mechanically verified repair are Critical 0,
High 0. The two Medium findings were recorded and did not restart review, as
required.
