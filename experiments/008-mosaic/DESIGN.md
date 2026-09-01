# MOSAIC Experimental Design

Design version: `SAIS/MOSAIC/DESIGN/1`

## Why a quartet instead of independent single trials?
The scientific contrasts of interest are source-label and presentation-order effects. Randomly comparing unrelated trials would mix those effects with different hidden truths and cue realizations.

MOSAIC therefore creates **counterfactual quartets**. Four fresh subject contexts receive the same numerical evidence about the same hidden capability, transformed only by label assignment and order.

This makes the final Bayes posterior a within-core invariant.

## Core lifecycle
Each core owns four fixed trial surfaces corresponding to:

- `canonical`
- `order_swap`
- `label_swap`
- `label_and_order_swap`

The quartet controller must treat these four surfaces as one randomization unit.

## Baseline barrier
The controller first publishes the common prior and configuration binding to all four surfaces.

Each fresh subject context returns one `p0` forecast. The controller does **not** create the core random key until all four baseline records are valid and publicly bound.

If any baseline is missing, refused, malformed, duplicated, or wrongly bound, the entire core aborts before hidden-state generation.
## Core randomization
After the baseline barrier, a cryptographically secure 256-bit core key derives domain-separated values for:

- capability truth `C`;
- cue-X correctness;
- cue-Y correctness;
- controlled payload;
- audit nonces.

Cue claims are produced from correctness bits and the frozen reliability profile. The key itself remains secret until the quartet is fully sealed.

The controller publishes a commitment to the same core realization on all four surfaces.

## Synchronized evidence phases
Phase 1 exposes the first transformed cue on each surface and waits for all four `p1` records.

Only after the quartet passes the first-cue barrier does phase 2 expose the second cue and wait for all four `p2` records.

Only after all four `p2` forecasts are sealed does the controller perform the controlled action.

This synchronization prevents one variant's public action or reveal from preceding another variant's forecast.

## Action and diagnosis
The synthetic P1 action is a deterministic function of the hidden capability and payload. All four variants therefore observe the same capability outcome.

Each subject context records a diagnosis after the action. The controller seals all four complete ledgers before publishing any hidden truth.
## Reveal and public verification
The reveal must allow an independent collector to reconstruct:

- the core key and derived truth;
- cue-X and cue-Y correctness;
- numerical reliabilities;
- per-variant label assignment;
- per-variant presentation order;
- each p0/p1/p2 source comment;
- controlled action;
- diagnosis;
- pre-reveal sealed Git objects.

Verification fails if the four ledgers do not share the same core realization or if any final Bayes comparator differs across transformations.

## Independence and contamination boundary
Quartet trials are paired experimental conditions, not independent statistical observations. Confirmatory inference must cluster or operate at the core level for label/order contrasts.

Each variant uses a fresh subject conversation. The subject is instructed to read only its designated issue. Persistent product memory, if enabled, is part of the recorded configuration and must be treated as a possible cross-trial channel rather than silently assumed absent. P1 should prefer a temporary/no-memory subject configuration if the product exposes one; otherwise cross-trial memory becomes a prespecified validity limitation.

Named and neutral frames are separate P1 cores. Their difference is therefore a secondary randomized pilot diagnostic, not a within-core causal contrast. Confirmatory frame comparisons should use matched evidence realizations if P1 justifies that question.

The current design conversation is excluded from all P1 subject data.

## Native-system extension
P1 validates the synthetic information structure. Later preregistrations may replace synthetic truth with real web, file, code, memory, connector, permission, or outage states. Native extensions require their own ground-truth adapters and cannot inherit P1 validity automatically.