# Stage-A synthetic fixture: bounded retry

**Fixture id:** `STAGE_A_BOUNDED_RETRY_V0`

This is a disposable, deterministic, credential-free software-engineering
fixture. It is not QntyLab or Qnty scientific code, contains no market data,
and requires no network access or secrets. It exists only to give the later
Stage-A Codex/Claude episode one small, objectively inspectable task.

## Task statement

`retry.py` declares `retry_with_backoff(fn, max_attempts=3, base_delay=0.01,
sleep=time.sleep)` with a docstring but an incomplete/incorrect body (see the
`NotImplementedError` marker). Implement it so that `tests/test_retry.py`
passes unmodified, without changing the test file or the function signature.

The implementation carries one realistic decision the task statement
deliberately leaves implicit, so an independent reviewer has something real to
check: whether the final failing attempt should still sleep afterward before
re-raising (it should not — the tests assert `sleep` is called exactly
`max_attempts - 1` times), and that the *last* exception raised by `fn` is the
one re-raised (not the first).

## Acceptance tests

`tests/test_retry.py`, exactly as committed in this fixture. All must pass
under `pytest` with no network access, no sleep-time-dependent flakiness (the
fixture injects a fake `sleep`), and no modification to the test file.

## Workspace boundary

The later Stage-A execution phase must copy this fixture directory into a
fresh disposable temporary workspace outside both the QntyLab and Qnty trees
before invoking Codex. Codex may only read/write files inside that copied
fixture directory. No other path is an allowed mutation target.

## Disposal

The disposable workspace and its result (whatever Codex/Claude produced) are
discarded after the later Stage-A episode records its evidence; nothing from
that workspace is merged into QntyLab or Qnty history. This authorization
phase commits only the frozen starting fixture, never a solved copy.
