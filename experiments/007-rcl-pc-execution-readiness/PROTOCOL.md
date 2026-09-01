# Stage 007 — RCL-PC Execution Readiness

Protocol version: `SMI-CP/RCL-PC/EXECUTION-READINESS/1`

Status: **PRE-EXECUTION ONLY**

Study freeze `sais-rcl-pc-v1` is invalidated and forbidden for execution. Stage 007 accepts only corrected freeze `sais-rcl-pc-v2`.

Stage 007 operationalizes the frozen Stage 006 positive-control block without starting any included behavioral trial.

## Purpose
Create a fail-closed execution ledger and deterministic public issue surfaces for the 32 fixed identifiers while preserving the scientific boundary between **preparation** and **observation**.

Creating an empty issue is not a trial start. A trial identifier becomes consumed only when controller dispatch is attempted.

## Frozen anchors
- study tag: `sais-rcl-pc-v2`
- reviewed freeze commit: `9cae514de94cd7d84ce9cfb293c209a91decb088`
- controller tag: `sais-rcl-bound-controller-v1` → `c899213eb5b3f68a77e399a9dd32a9f86a827824`
- configuration commit: `b6a1e728f9ced540306b604dece5e42465b46073`
- configuration path: `experiments/006-rcl-pc-final-freeze/CONFIG.json`
- configuration binding: `6d09daad4c45c1976794add2c7a404aca0e3f27fca1946ad467b900b00d85caa`
- fixed identifiers: `PC-RCL-001` … `PC-RCL-032`

## Registry states
`NOT_CREATED → ISSUE_CREATED → DISPATCH_ATTEMPTED → READY_PUBLISHED → REVEALED → COLLECTED`

An execution failure after dispatch may transition to `ABORTED`. `ABORTED` and `COLLECTED` are terminal.
## Safety invariants
- The registry stores no hidden assignment, key, condition, legibility, or payload hash.
- Issue provisioning cannot dispatch the controller.
- Dry-run is the default mode.
- `--apply` requires the exact freeze-tag confirmation.
- The local freeze tag must resolve to the registry's reviewed freeze commit.
- The controller tag must resolve to the frozen controller commit.
- The configuration source commit must be an ancestor of the reviewed freeze commit.
- Existing issue surfaces are reused only when title, marker, body, and zero-comment state match exactly.
- Issue numbers are unique and identifiers are never recycled.
- The registry is saved after each successful issue creation/reconciliation for crash-safe recovery.
- `included_trials_started` must remain zero throughout Stage 007.

## Scientific boundary
This stage creates no capability assignment and collects no forecast, probe, action, diagnosis, or outcome. It therefore does not alter the Stage 006 statement that no included trial has started.

The current design conversation remains ineligible as an included subject context. Actual Stage 008 execution requires a fresh conversation per identifier under the frozen subject instructions.