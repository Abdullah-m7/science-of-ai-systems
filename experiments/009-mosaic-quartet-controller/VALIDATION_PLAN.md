# Stage 009 Validation Plan

Status: **LOCAL MECHANICS PASS; PUBLIC VALIDATION NOT AUTHORIZED**

## Local adversarial suite
`tests/test_mosaic_controller.py` exercises the candidate with an in-memory issue transport and synthetic Bayesian subject.

Required cases:

1. successful quartet with all global phase barriers;
2. malformed first p0 cannot be repaired and cannot trigger key generation;
3. duplicate p1 blocks progression and reveal;
4. final immutable-seal failure prevents reveal;
5. baseline immutable-seal failure prevents randomization;
6. tampered design transform is rejected before any post;
7. tampered sealed cue fails verification;
8. tampered revealed key fails verification;
9. unstructured subject commentary blocks randomization;
10. verifier failure after final seal prevents key reveal;
11. destructive seal callbacks cannot mutate controller state;
12. full-design hash mismatch is rejected before READY;
13. trial/variant swaps are rejected against the frozen matrix;
14. randomization is domain-separated by core/study/design;
15. quartet commitment binds baseline-seal context;
16. baseline-seal reference substitution breaks commitment verification;
17. seal-envelope failure prevents public SEAL and REVEAL;
18. seal-envelope substitution breaks verifier checks.

The full repository suite must also pass on the candidate branch.

## Public validation prerequisites
A future public excluded validation requires a new stage. It must not reuse P1 behavioral identifiers.
Before such validation:

- freeze the transport implementation and controller code to an immutable tag;
- use four dedicated public validation issues with non-P1 identifiers;
- commit the baseline ledger, final quartet ledger, and final seal envelope as separate exact Git objects before the relevant public phases;
- collect full public comment histories, including author and edit metadata;
- fetch the baseline ledger, final ledger, and seal-envelope bytes from their exact Git commits rather than workflow artifacts;
- verify the four issue transcripts, full-design hash, context-bound core-key derivation, cue records, action, baseline seal, final ledger seal, seal-envelope seal, and reveal from outside the controller run;
- permanently exclude validation records from P1 behavioral analysis.

## HOLD conditions
Public controller validation may be engineered while RCL-PC is unfinished, but **MOSAIC P1 behavioral execution remains prohibited** until the Stage 008 execution gate is opened by an RCL-PC final `PASS` and all other frozen prerequisites.

No controller workflow is added by Stage 009.