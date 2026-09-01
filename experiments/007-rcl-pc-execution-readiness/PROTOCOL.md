# Stage 007 — RCL-PC Execution Readiness

Protocol version: `SMI-CP/RCL-PC/EXECUTION-READINESS/1`

Status: **PRE-EXECUTION ONLY**

Stage 007 operationalizes the frozen Stage 006 positive-control block without starting any included behavioral trial.

## Purpose
Create a fail-closed execution ledger and deterministic public issue surfaces for the 32 fixed identifiers while preserving the scientific boundary between **preparation** and **observation**.

Creating an empty issue is not a trial start. A trial identifier becomes consumed only when controller dispatch is attempted.

## Frozen anchors
- study tag: `sais-rcl-pc-v1`
- reviewed freeze commit: `332075e3b887053c641f19b41f410e8f2c4721ee`
- controller tag: `sais-rcl-bound-controller-v1`
- configuration commit: `9bd28da4b8755b0807bb7b6952f1e6d4c447a0b6`
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
- Existing issue surfaces are reused only when title, marker, body, and zero-comment state match exactly.
- Issue numbers are unique and identifiers are never recycled.
- The registry is saved after each successful issue creation/reconciliation for crash-safe recovery.
- `included_trials_started` must remain zero throughout Stage 007.

## Scientific boundary
This stage creates no capability assignment and collects no forecast, probe, action, diagnosis, or outcome. It therefore does not alter the Stage 006 statement that no included trial has started.

The current design conversation remains ineligible as an included subject context. Actual Stage 008 execution requires a fresh conversation per identifier under the frozen subject instructions.