# Stage 009 — MOSAIC Quartet Controller Candidate

Protocol: `SAIS/MOSAIC/CTRL-CANDIDATE/1`

Status: **LOCAL CANDIDATE — PUBLIC DISPATCH DISABLED**

Stage 009 implements the quartet state machine required by MOSAIC without adding a GitHub Actions workflow or starting a P1 trial.

## Scientific invariant
A MOSAIC core consists of four counterfactual variants that share one hidden capability and two cue realizations. The controller must prevent later public phases from leaking information into earlier forecasts.

The lifecycle is:

`EMPTY → READY×4 → P0×4 → BASELINE_SEAL → P0_SEAL×4 → RANDOMIZE → CORE_COMMIT×4 → CUE1×4 → P1×4 → CUE2×4 → P2×4 → ACTION×4 → DIAGNOSIS×4 → LEDGER_SEAL → SEAL_ENVELOPE → SEAL×4 → VERIFY → REVEAL×4`

No phase may cross its quartet barrier.

## Clean-surface preflight
Before `READY`, the candidate requires:

- exactly four design rows and four distinct issue clients;
- four distinct issue numbers;
- one exact `canonical`, `order_swap`, `label_swap`, and `label_and_order_swap` row;
- no pre-existing issue comments;
- no hidden truth or cue claim already present in the design shell.
The row validator regenerates the complete frozen 64-row design, requires the supplied `design_hash` to equal its canonical hash, and requires each quartet row to equal its exact frozen row by `trial_id`. A cryptographically valid ledger is not sufficient if a trial/variant assignment, label, order, frame, or reliability differs from the design.

## Baseline-before-randomization barrier
All four subjects first receive the same disclosed prior `P(C=available)=0.50` and return one closed-field `p0` record.

The first prefixed response is binding. A malformed first response cannot be skipped in favor of a later correction. Duplicate protocol responses, premature later-phase responses, or unstructured subject commentary are protocol violations.

After all four valid p0 records exist, the controller:

1. computes a canonical p0-bundle hash;
2. sends the complete baseline ledger to an external immutable-seal callback;
3. requires a non-empty immutable reference;
4. publishes `SAIS_MOSAIC_P0_SEAL` on all four surfaces;
5. only then calls the cryptographic key generator.

Therefore the hidden core assignment cannot legitimately exist before the publicly referenced baseline seal.

## Hidden realization
The 256-bit core key derives, by HMAC domain-separated over protocol + `core_id` + study binding + full-design binding:

- binary capability truth;
- cue-X correctness;
- cue-Y correctness;
- controlled payload.

Cue correctness is sampled against the design's frozen numerical reliabilities. One realization is reused across the four counterfactual transformations. The public quartet commitment additionally binds the core key to the core identity, study/design hashes, p0 bundle, baseline hash, and immutable baseline-seal reference.
## Evidence barriers
Cue 1 is posted to all four surfaces before the controller accepts any transition to cue 2.

All four `p1` records must be valid, uniquely present, and bind the exact first-cue hash. Only then may cue 2 be posted.

All four `p2` records must bind the canonical two-cue transcript. Only after all four are valid and unique may the controlled action occur.

The controlled action is the same function of the shared core truth on every variant.

## Final seal and reveal
After four diagnoses, the controller audits the subject transcript again. Each issue must contain exactly one subject `P0`, `P1`, `P2`, and `DIAGNOSIS`, with no unstructured subject comments.

The complete quartet ledger is passed as a detached JSON copy to the final ledger-seal callback. Callback mutation therefore cannot modify controller state. After its immutable ledger reference is returned, the controller builds a separate **seal envelope** binding the ledger hash, ledger reference, baseline seal, design/study bindings, and quartet commitment. A second immutable callback seals that detached envelope.

Only after both non-empty immutable references exist does the controller publish four `SEAL` messages containing the ledger hash/reference and seal-envelope hash/reference. It then constructs the reveal object but runs `verify_sealed_quartet` **before publishing the core key**.

A failed verifier prevents all reveal comments. Only a verified sealed ledger can publish `REVEAL`.

## Local verifier
The verifier independently re-derives the hidden realization from the revealed key and checks:

- context-bound key commitment;
- baseline hash and p0-bundle hash;
- study binding plus exact regeneration of the frozen 64-row design;
- all four design transformations;
- exact expected cues;
- p0/p1/p2/diagnosis record bindings;
- action outcome;
- final ledger hash and seal-envelope object/hash;
- per-issue temporal ordering;
- one-response-only transcript audit;
- unique issue numbers;
- equality of the final Bayesian comparator across all four variants.
## Candidate boundary
This is not yet a public controller. No `.github/workflows/*mosaic*` workflow exists.

The immutable-seal callbacks are abstractions in Stage 009. Before any behavioral pilot, a later stage must bind the baseline ledger, final quartet ledger, and final seal envelope to exact public Git objects; verify issue authorship and edit metadata from live GitHub evidence; freeze controller code to a tag; and independently recollect the quartet.

Stage 008's execution gate remains authoritative. RCL-PC must return final `PASS` before MOSAIC P1 behavioral dispatch is permitted.

Local tests use deterministic synthetic subjects and injected keys only to challenge mechanics. They are not MOSAIC P1 data and cannot support a behavioral claim.