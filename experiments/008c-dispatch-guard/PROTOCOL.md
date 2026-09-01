# Stage 008C — Fail-Closed Single-Trial Dispatch Guard

Protocol: `SMI-CP/RCL-PC/DISPATCH/1`

Status: **PRE-DISPATCH IMPLEMENTATION — NO INCLUDED DISPATCH HAS OCCURRED**

## Purpose
Make the transition from an empty public issue surface to a live RCL-PC trial recoverable under network, process, or client interruption.

The core rule is:

> Durable reservation must precede external workflow dispatch.

A reservation consumes the fixed identifier for retry purposes but creates no hidden capability or legibility assignment. The controller still generates its fresh 256-bit trial key only after Forecast0 is bound.

## Authoritative anchors
- study freeze: `sais-rcl-pc-v2`
- controller: `sais-rcl-bound-controller-v1`
- workflow: `.github/workflows/rcl-bound-controller.yml`
- live dispatch journal branch: `rcl-dispatch-ledger`
- fixed order: `PC-RCL-001` through `PC-RCL-032`
- maximum concurrent dispatches: `1`

## Dispatch sequence
1. Validate the frozen manifest, registry, handoff manifest, and dispatch plan.
2. Verify the dedicated issue still has the exact frozen title/body and zero comments.
3. Verify the exact precommitted handoff bytes for this identifier.
4. Verify no matching controller workflow run is currently active.
5. Record the complete baseline set of matching workflow run IDs.
6. Persist and push a `RESERVED` record to `rcl-dispatch-ledger`.
7. Only after that push succeeds, submit one GitHub workflow dispatch from the frozen controller tag.
8. Persist dispatch-command outcome.
9. Identify the unique new matching workflow run relative to the baseline and persist its run ID/URL.
10. Never automatically redispatch a reserved identifier.
## Uncertainty policy
If the dispatch command fails, times out, or returns an uncertain transport result, the identifier remains reserved. The guard may inspect GitHub for a matching new run, but it may not blindly retry.

If zero matching new runs are discovered after the polling window, record `RUN_UNRESOLVED`. If more than one appears, record `RUN_AMBIGUOUS`. Both states require explicit controller review and consume the identifier unless public evidence proves no trial execution occurred.

## Trial-order policy
Only the next fixed identifier may be reserved. Before `PC-RCL-NNN`, every earlier identifier must have a terminal dispatch-ledger state (`REVEALED`, `COLLECTED`, or `ABORTED`). No two included trials may be active concurrently.

## Subject boundary
Reservation and dispatch administration occur outside the subject conversation. Once a run is identified and `SAIS_RCL_READY` is published, the administrator supplies only the already precommitted handoff packet to a newly opened regular ChatGPT conversation.

The current design/controller conversation is not an eligible subject context.

## Product-state confirmation
Apply mode requires explicit operator confirmations matching the frozen v2 values for model label, client build, memory state, and customization state. A mismatch blocks dispatch before reservation.

## Non-goals
This guard does not alter the frozen controller, does not generate the hidden trial key, does not answer Forecast0/Forecast1/Diagnosis, and does not compute behavioral results.