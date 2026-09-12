# QntyLab Clean TSMOM EXP_V2 R3 implementation freeze

## R2 implementation defect receipt

R2 was synthetic-only, required `SYNTHETIC_FIXTURE`, ignored binding paths,
and its result verifier authenticated and copied producer artifacts rather
than reading source data and independently recomputing results. Its
`max_abs_difference=0.0` was not independent numerical evidence. The defect
is classified as `RECOVERABLE_PREREGISTRATION_EXECUTION_IMPLEMENTATION_DEFECT`.

## R3 execution binding

`REAL_EXECUTION_IMPLEMENTATION_R3` changes execution implementation only.
R1 source bytes and authentication remain unchanged. R2 timeline, window,
metrics, benchmark, and classification semantics remain unchanged. No real
corrected metrics existed or were inspected before R3 was frozen.

`market_data_network_attempts_during_r3_freeze=0`
`real_strategy_evaluation_attempts_during_r3_freeze=0`
`corrected_metrics_observed=0`
`source_bundle_byte_changes=0`
`v2_contract_changes=0`
`v2r1_contract_changes=0`
`v2r2_contract_changes=0`

## Behavioral coverage matrix

The artificial bundle is deterministic, authenticated through the R1 binding,
contains no `SYNTHETIC_FIXTURE` marker, and is used through the R3 producer and
independent verifier entry points. The 31 required behaviors are covered by
the following test nodes:

| requirement | test node ID | kind | polarity | result |
|---|---|---|---|---|
| 1-4 routing and required roots | `test_valid_authenticated_artificial_bundle_passes`; `test_required_roots_are_explicit_and_missing_roots_fail` | behavioral | positive/hostile | PASS |
| 5-9 contract, binding, semantics and R3 mutations | `test_altered_contract_or_binding_payload_or_sidecar_fails` | behavioral | hostile | PASS |
| 10-17 source manifest, bytes, files, symbols and checkout substitution | `test_source_bundle_hostile_mutations_fail`; `test_checkout_local_substitution_is_rejected`; `test_source_manifest_must_be_bound_to_r1_material` | behavioral | hostile | PASS |
| 18 output routing | `test_nonempty_output_directory_is_rejected` | behavioral | hostile | PASS |
| 19-23 independent source root, source authentication and V1/V2/funding mutation rejection | `test_verifier_requires_own_source_root_and_recomputes_artifacts`; `test_verifier_rejects_mutated_producer_artifact_values` | behavioral | positive/hostile | PASS |
| 24-27 turnover, costs, equity and metrics mutation rejection | `test_verifier_rejects_mutated_producer_artifact_values` | behavioral | hostile | PASS |
| 28-29 benchmark and classification/comparison mutation rejection | `test_verifier_rejects_mutated_producer_artifact_values` | behavioral | hostile | PASS |
| 30-31 behavioral controls, artifact manifest and missing artifact | `test_verifier_rejects_missing_artifact`; `test_verifier_rejects_mutated_artifact_manifest_digest`; `test_controls_are_evidence_bearing_not_unsupported_constants` | behavioral | hostile/positive | PASS |

`r3_required_behaviors_total=31`
`r3_required_behaviors_covered=31`
`r3_required_behaviors_uncovered=0`

## R3 verification receipt

`focused_R3_tests_pass=1`
`strict_R3_tests_pass=1`
`producer_determinism_pass=1`
`independent_recomputation_pass=1`
`maximum_independent_difference=0.0`
`real_strategy_evaluation_attempts_during_r3_coverage=0`

The repository-wide suite retains 73 baseline-reproduced red tests caused by
missing external research fixtures and caches. R3 introduces no additional
failing or erroring test nodes. No real producer or full verifier invocation
was performed.
