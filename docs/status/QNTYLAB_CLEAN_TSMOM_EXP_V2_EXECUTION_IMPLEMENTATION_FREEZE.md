# QntyLab Clean TSMOM EXP_V2 execution implementation freeze

The scientific contract remains byte-identical to commit `9a5396ba0aa9403f324ac70e003208ec9ff1ce47`. The prior evaluation attempt produced no results because the executable producer, deterministic artifact writer, and independent result verifier were absent.

This implementation-freeze follow-up adds only execution infrastructure: a local-only producer core and CLI, deterministic artifact and implementation contracts, an independent verifier boundary, and synthetic hostile tests. Synthetic fixtures are used for implementation testing. No retained real source was evaluated, no market-data request was made, and no corrected metrics were observed.

The implementation and artifact-contract hashes are frozen in the accompanying manifests. A later explicit authorization is required for the single real evaluation; this freeze does not authorize that run.
