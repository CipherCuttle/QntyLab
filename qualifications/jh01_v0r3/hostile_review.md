# V0R3 hostile review

Reviewed frozen candidate after isolated verification. No Critical or High findings: policy constants are source constants; `Verify` precedes all statement access; signer URI and RFC3161 TSA result are checked from the verification result; identity extension fields, exact unique subjects, and independently hashed asset are fail-closed. The verifier has no network code and was executed in an unshared network namespace. The only authority granted is one later bounded recorder qualification phase.

Medium: `sigstore-go` permits deployment-specific verifier configuration; V0R3 intentionally requires the verified GitHub TSA observer timestamp, rather than unrelated Rekor/SCT material absent from this release bundle. This does not widen acceptance.
