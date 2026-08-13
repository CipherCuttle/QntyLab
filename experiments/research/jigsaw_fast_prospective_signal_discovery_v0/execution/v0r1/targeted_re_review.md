# JFP03 V0R1 Historical Scientific Execution Authorization — Targeted Re-review

This is the single permitted targeted re-review. It is bounded strictly to initial findings HIGH-01, HIGH-02, and MEDIUM-01. It did not open any object under `data/archive`, call `execute_once` or `load_frozen_klines`, compute a historical result, or use network/source access.

## Verdict

`BLOCKED_AUTHORIZATION_CLOSURE`

Residual severity counts:

- CRITICAL: 0
- HIGH: 1
- MEDIUM: 0
- LOW: 0

HIGH-01 and MEDIUM-01 are closed. HIGH-02 remains incomplete, so authorization closure may not proceed. This targeted re-review is exhausted; no further review recursion is authorized.

## HIGH-01 — Closed

The repaired authorization is explicitly narrowed to one unique execution workspace and Git common directory:

- workspace root `/home/swirky/DevHub/repos/QntyLab`;
- Git common directory `/home/swirky/DevHub/repos/QntyLab/.git`;
- common-directory device `66307` and inode `7740500`;
- claim path `qntylab-claims/jfp03-v0r1-historical-scientific-execution-v0.json` relative to that common directory.

These values are frozen in the executor contract (`qntylab/jfp03_v0r1_historical_scientific_execution.py:46-64,543-552`), authorization (`historical_scientific_execution_authorization.json:31-52`), and canonical project (`docs/state/projects.toml:29-37`). `workspace_identity` resolves the real Git top level/common directory and stats the common directory for device and inode (`qntylab/jfp03_v0r1_historical_scientific_execution.py:222-247`). `verify_frozen_bindings` checks the full actual identity against the frozen constants and authorization before returning the shared claim path (`qntylab/jfp03_v0r1_historical_scientific_execution.py:636-723`).

`execute_once` verifies first, creates the claim second, and opens frozen sources only afterward (`qntylab/jfp03_v0r1_historical_scientific_execution.py:944-953`). `claim_execution` performs compare-create with `O_EXCL`, fsyncs the claim and parent directory, and intentionally preserves the file after every post-create `BaseException` (`qntylab/jfp03_v0r1_historical_scientific_execution.py:726-779`). Consequently a failure after creation consumes the run, and linked worktrees sharing this common directory compete on one filesystem object. The two-root synthetic test confirms one winner and a replay failure (`tests/test_jfp03_v0r1_historical_scientific_execution_authorization.py:312-325`).

The explicit narrower authority closes the cross-clone issue: an independent clone has a different workspace/common-directory path and device/inode identity, so it fails verification and is outside the authorized execution scope. The authorization does not purport to grant portable cross-clone execution authority. This is compatible with network-free scientific execution.

## HIGH-02 — Not closed

The repair now freezes and pre-claim verifies:

- CPython implementation and version;
- Linux system label;
- `x86_64` architecture and byte order;
- exact NumPy version;
- BLAS and LAPACK names/versions;
- SHA-256 of the complete `numpy.__config__.CONFIG` object.

Those values appear in the executor contract and authorization, their digest is bound in the canonical project, drift is rejected before claim/source access (`qntylab/jfp03_v0r1_historical_scientific_execution.py:196-219,636-664`), and the verified identity is emitted in both claim and result (`qntylab/jfp03_v0r1_historical_scientific_execution.py:739-759,898-926`). The NumPy drift test fails closed before claim (`tests/test_jfp03_v0r1_historical_scientific_execution_authorization.py:120-124`).

However, the requested **exact platform and Python build identity** is still not frozen. The identity records only `platform_system = Linux` and `machine = x86_64`; it omits the kernel/platform release, libc implementation/version, Python compiler/build identity, and implementation cache/ABI tag. The actual environment reports Linux `7.0.0-29-generic`, glibc `2.43`, GCC `15.2.0`, and cache tag `cpython-314`, none of which is authenticated by `FROZEN_RUNTIME_IDENTITY`. This executor calls Python `math.log`, `math.sqrt`, and `math.erfc` as well as NumPy linear algebra, so libm/Python-build drift can affect scientific values or an inclusive threshold even when the currently frozen subset matches.

Required correction: add and freeze exact platform release/version, libc identity/version, Python compiler/build/ABI identity (or replace them with a hermetic immutable runtime/container digest that binds these facts); include them in contract, authorization, and canonical binding; verify them before the claim; emit them in claim/result; and extend drift tests beyond only `numpy_version`.

## MEDIUM-01 — Closed

`multiplicity_family` now requires the actual JFP03 terminal classification and enforces that successful/no-support classifications have non-null p-values while blocked classifications have null p-values (`qntylab/jfp03_v0r1_historical_scientific_execution.py:514-530`). Every terminal path supplies its own classification (`qntylab/jfp03_v0r1_historical_scientific_execution.py:954-990`). Tests cover supported/no-support status, blocked JFP03 nulls, and JFP01/JFP02 null scientific values (`tests/test_jfp03_v0r1_historical_scientific_execution_authorization.py:293-309`).

## Verification

- Synthetic/metadata-only targeted and project-context tests: `47 passed`.
- `python -m qntylab.project_context`: active project `none`; no authority warnings.
- Executor SHA, executor-contract digest, authorization self-digest, frozen-runtime subset/digest, and workspace identity all recomputed and matched the staged authorization.

No real scientific value or historical result was computed.
