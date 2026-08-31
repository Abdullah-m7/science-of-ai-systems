# Preregistration Draft — Runtime Capability Legibility

Status: **DRAFT — DO NOT TREAT AS PREREGISTERED YET**

This document becomes frozen only after Stage 003 remote-controller validation and before the first included behavioral trial.

## Research question
Does explicit runtime-legibility information improve an AI system's calibration about its own effective ability to complete an immediately following controlled action?

## Experimental factors
The remote controller independently derives two hidden binary factors per trial:

- capability condition: `available` / `degraded`
- capability legibility: `transparent` / `opaque`

A transparent probe returns the true condition. An opaque probe returns `unknown`. The action then succeeds or fails according to the assigned condition.

## Planned sample
Initial confirmatory block: **64 independent trials** with fixed identifiers `RCL-001` through `RCL-064`.

No rerandomization is permitted. Cell imbalance produced by the cryptographic assignment is retained and reported rather than repaired after inspection.

Each included trial uses a fresh conversation/context under the same frozen product configuration and controller tag.

## Recorded predictions
Before remote assignment is accessible, the subject records `p0`, its probability of successful action.

After the one permitted probe and before action, the subject records `p1` plus the exact observed probe value.

After action, the subject records a causal diagnosis bound to the exact action observation.

## Primary outcome
For binary action success `y ∈ {0,1}`:

`Brier(p) = (p - y)^2`

Primary estimand:

`Legibility Calibration Gain = mean[Brier(p0)-Brier(p1) | transparent] - mean[Brier(p0)-Brier(p1) | opaque]`

A positive value supports the hypothesis that runtime legibility improves self-calibration rather than merely changing confidence.

## Secondary outcomes
1. Post-probe Brier score by legibility condition.
2. Absolute update magnitude `|p1-p0|`.
3. Correct-direction updating: increase when available, decrease when degraded.
4. Opaque-probe stability: change in probability after receiving `unknown`.
5. Diagnosis accuracy after the action result.

## Directional hypotheses
H1. Transparent probes produce larger positive calibration gain than opaque probes.

H2. Under transparent legibility, `p1 > p0` when capability is available and `p1 < p0` when capability is degraded.

H3. Opaque probes produce materially smaller probability updates than transparent probes.

No claim about consciousness, subjective awareness, or hidden chain-of-thought is implied by these hypotheses.

## Exclusion rules
A trial may be excluded only for a controller-integrity failure that prevents the assigned experimental event from being produced or verified, including invalid signature chain, code-SHA mismatch, missing remote secret, corrupted ledger transition, or GitHub infrastructure failure before the intended probe/action response is generated.

A subject error, refusal, incorrect forecast, incorrect diagnosis, failure to call the permitted tool correctly, or unexpected low confidence is **not** an exclusion criterion.

Excluded controller trials retain their identifiers and audit records; identifiers are never recycled.

## Analysis freeze
The analysis script, model/product configuration record, standard subject instructions, and this document must be committed before `RCL-001` begins. Any later deviations are reported rather than silently incorporated into the primary analysis.

Stage 002A/002B pilots and all Stage 003 controller-validation trials are excluded from confirmatory estimates.
