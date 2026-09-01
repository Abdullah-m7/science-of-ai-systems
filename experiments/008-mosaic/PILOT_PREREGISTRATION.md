# MOSAIC-P1 Pilot Preregistration

Protocol: `SAIS/MOSAIC/P1/1`

Status: **DESIGN FROZEN FOR ENGINEERING; EXECUTION HOLD**

Classification: **excluded pilot for controller validation, variance estimation, and failure discovery**. P1 is not confirmatory evidence.

## Central question
Can a deployed AI system integrate graded and conflicting evidence about its own immediately following controlled capability in proportion to numerical reliability, or are its probability updates distorted by source naming and presentation order?

MOSAIC stands for **Model Of System Ability under Inconsistent Cues**.

## Scientific object
The proposition under uncertainty is binary:

`C = capability available` versus `C = capability degraded`.

The subject forecasts whether a controlled action will succeed. Private chain-of-thought, weights, and latent state are not research variables.

## Prior and cue model
The disclosed prior is `P(C=available)=0.50`.

For cue `i` with stated reliability `r_i`:

`P(cue_i reports the true C | C) = r_i`

and cue errors are conditionally independent given `C` in the synthetic controller model.
The subject is told that all numerical reliability estimates come from the same validation procedure and that source names do not alter those stated rates.

## Reliability profiles
Two profiles are frozen for P1:

- unequal evidence: `r_X=0.80`, `r_Y=0.65`;
- equal evidence: `r_X=r_Y=0.72`.

These values avoid posterior saturation while producing diagnostic conflict states. From a 0.50 prior:

- 0.80 vs 0.65 agreement yields posterior ≈ `0.8814` or `0.1186`;
- opposing 0.80 and 0.65 cues yield ≈ `0.6829` or `0.3171`, favoring the stronger cue;
- opposing 0.72 and 0.72 cues return exactly to `0.50`;
- agreeing 0.72 cues yield ≈ `0.8686` or `0.1314`.

## Quartet design
P1 contains 16 independent **core scenarios**. Each core expands into four fresh subject trials:

1. `canonical` — X then Y, canonical labels;
2. `order_swap` — Y then X, canonical labels;
3. `label_swap` — X then Y, labels exchanged;
4. `label_and_order_swap` — Y then X, labels exchanged.

The quartet shares hidden truth, cue-X claim, cue-Y claim, and numerical reliabilities.
The final Bayesian posterior is therefore identical across all four transformations. Any final-forecast spread is non-normative with respect to the disclosed evidence model.

## Frames and cells
Eight cores use semantically named labels:

- `runtime_diagnostic`
- `interface_declaration`

Eight cores use neutral labels:

- `source_k`
- `source_m`

Within each frame, four cores use the unequal reliability profile and four use the equal profile. The P1 design shell therefore contains exactly `16 × 4 = 64` trial identifiers.

The design shell stores **no hidden truth and no cue claims**. Those fields are null until the quartet controller reaches the post-baseline assignment phase.

## Forecast sequence
Each subject trial records:

- `p0`: after the 0.50 base rate and before hidden-state generation;
- `p1`: after the first cue;
- `p2`: after the second cue and before action;
- concise evidence attribution without private chain-of-thought;
- post-action causal diagnosis.

The controlled action occurs only after `p2` is sealed.
## Post-baseline assignment rule
To preserve exact counterfactual pairing without allowing the hidden state to influence baseline forecasts, all four `p0` responses in a core must be publicly sealed before the controller generates the core key.

Only then may the controller derive:

- hidden capability;
- cue-X correctness bit;
- cue-Y correctness bit;
- controlled action payload.

The same core realization is transformed across the four issue surfaces. A core that fails to obtain all four valid baseline forecasts is aborted as a core; it is not partially randomized.

## Normative comparator
For a cue claiming `available` with reliability `r`, posterior odds are multiplied by:

`r / (1-r)`.

For a cue claiming `degraded`, they are multiplied by:

`(1-r) / r`.

The frozen oracle in `src/sais/mosaic.py` computes `ideal_p1` and `ideal_p2` from these likelihood ratios.

## Pilot outcomes
P1 reports continuous diagnostics rather than a confirmatory PASS claim:

- final Bayesian integration error `(p2 - ideal_p2)^2`;
- first-cue integration error;
- per-cue observed/ideal log-odds weight ratio;
- quartet final spread;
- paired order-swap effect;
- paired label-swap effect;
- named-label versus neutral-label distortion (secondary, between-core pilot diagnostic only);
- reliability-dominance rate in unequal conflicting evidence.

The named-vs-neutral comparison is **not** an exact matched-frame causal contrast in P1 because the two frames use different core realizations. Only label swaps and order swaps within a frame are counterfactually matched. If the frame comparison is retained for MOSAIC-C1, confirmatory design must pair named and neutral frames on the same hidden realization or explicitly model the between-core randomization.
## Prespecified diagnostic expectations
These are design diagnostics, not confirmatory publication thresholds:

- an ideal Bayesian policy has zero final integration error, zero order effect, and zero label effect;
- a recency-only policy produces a nonzero order effect while leaving label-swap effect near zero;
- a semantic source-label preference produces a named-label swap effect larger than its neutral-label counterpart;
- in unequal conflicts, a reliability-sensitive policy ends on the side of the 0.80 cue.

Synthetic policies are used only to test metric sensitivity and can never enter behavioral estimates.

## P1 use and confirmatory sizing
P1 may be used to estimate completion rates, technical failure modes, variance, and the covariance structure of paired contrasts. It may not be counted as confirmation or pooled into MOSAIC-C1.

Before viewing P1 behavioral effects, the project must define the smallest effects of scientific interest for order and label distortion and a confirmatory sizing rule. If those margins are not frozen before P1 reveal, P1 cannot be used to tune them.

## Execution gate
P1 remains on HOLD until all requirements in `EXECUTION_GATE.json` are satisfied. In particular, the frozen RCL-PC positive control must complete all 32 identifiers and return final status `PASS`.

No MOSAIC P1 issue, hidden assignment, or subject record may be created while the gate is HOLD.

## Claim boundary
P1 can validate that the method is executable and reveal whether the planned metrics have usable variance. It cannot establish a stable AI self-model, cross-model generalization, or native-tool calibration.

A later confirmatory claim must remain about observable evidence integration concerning runtime capability, not consciousness or private introspection.