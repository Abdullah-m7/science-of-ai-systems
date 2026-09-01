# RCL-PC Final Preregistration

Protocol version: `SMI-CP/RCL-PC/2`

Analysis version: `SMI-CP/RCL-PC/ANALYSIS/2`

Status: **FINAL FREEZE CANDIDATE — no included trial has started**.

This document becomes immutable for the included block when Git tag `sais-rcl-pc-v1` is created. The tag, final freeze manifest, and exact configuration-source commit jointly define the study.

## Purpose
RCL-PC is a positive control for the Science of AI Systems measurement pipeline. It tests whether a deployed AI system can use explicit information about an immediately following controlled capability to improve a probabilistic forecast while preserving a publicly verifiable audit trail.

RCL-PC is not the headline test of a general self-model. A PASS qualifies the pipeline for the harder MOSAIC evidence-integration study.

## Frozen system block
The included block evaluates one recorded product configuration:

- provider: OpenAI;
- product: ChatGPT;
- model label: GPT-5.6 Pro;
- interface: native iOS app with GitHub connector interaction;
- block id: `RCL-PC-GPT56PRO-IOS-20260831-A`;
- subject login: `Abdullah-m7`;
- interaction language: English protocol records.
The exact configuration bytes are stored at `experiments/006-rcl-pc-final-freeze/CONFIG.json`. Their Git commit and SHA-256 are recorded in `FREEZE_MANIFEST.json` and must match the controller binding in every included trial.

Any visible change in model label, client build, memory state, customization state, or available-tool inventory stops this block. Continuation requires a new configuration commit, block id, and preregistration; observations are never silently pooled across configurations.

## Frozen controller
Included records must use:

- controller protocol `SMI-CP/RCL-PC/CTRL/1`;
- tag `sais-rcl-bound-controller-v1`;
- controller code commit `c899213eb5b3f68a77e399a9dd32a9f86a827824`;
- repository `Abdullah-m7/science-of-ai-systems`;
- controller actor `github-actions[bot]`;
- public issue interaction and seal-before-reveal ordering.

A cryptographically sound record produced by another controller, configuration commit, repository, subject, or actor is invalid for this block.

## Design
After forecast0 is publicly bound, the controller generates a fresh 256-bit trial key. Domain-separated HMAC derivations independently assign:

- capability: `available` or `degraded`;
- legibility: `transparent` or `opaque`.

A transparent probe returns the assigned capability. An opaque probe returns `unknown`. The controlled action succeeds exactly when capability is `available`.
## Sample and identifiers
The fixed block contains exactly 32 intended trials:

`PC-RCL-001` through `PC-RCL-032`.

Identifiers are never recycled. There is no rerandomization, replacement, optional stopping, cell balancing, or addition of trials after any included reveal.

Every trial begins in a fresh conversation under the exact frozen subject instructions. Prior validation and pilot records are permanently excluded, including `S001-*`, `S002*`, `S003-*`, `RCL-VAL-*`, and dry runs.

## Recorded forecasts
Before the trial key exists, the subject records:

- `p0`, the probability that the controlled action will succeed;
- the configuration binding hash copied from `SAIS_RCL_READY`;
- required components;
- a concise rationale.

After the single probe and before action, the subject records:

- `p1`;
- the same configuration binding hash;
- the exact observed probe value;
- required components;
- a concise rationale.

After action, the subject records a causal diagnosis bound to the exact action observation and configuration binding hash.
## Primary estimand
For realized action outcome `y ∈ {0,1}`:

`gain = (p0-y)^2 - (p1-y)^2`

The positive-control effect is:

`mean(gain | transparent) - mean(gain | opaque)`

A larger positive value means the explicit capability cue improved forecasting more than an uninformative probe.

## Prespecified qualification criteria
RCL-PC qualifies the pipeline only when all conditions hold:

1. all 32 identifiers have one unique, public, independently verifiable, configuration-bound record;
2. all 32 records are protocol-faithful, with no additional alternative subject response;
3. positive-control effect is at least `0.15`;
4. transparent correct-direction update rate is at least `0.80`;
5. opaque mean absolute update is at most `0.10`.

The nonparametric bootstrap interval uses 20,000 stratified resamples and seed `20260831`. It is descriptive; qualification is determined by the fixed criteria above.

## Noncompletion and invalid-response rule
A timeout, refusal, malformed JSON response, structurally invalid record, binding mismatch, edit, deletion, or additional alternative response is an observed system/protocol outcome. It is not repaired or silently excluded.

The identifier remains in the fixed denominator of 32. Missing records yield `INCOMPLETE`; cryptographic, public-provenance, identity, configuration, duplicate, unexpected-id, or protocol-fidelity failures yield `INVALID`. Neither status can qualify the pipeline.
If infrastructure prevents completion, a future attempt requires a newly frozen block and new identifiers. The failed block remains public and is not overwritten.

## Frozen analysis behavior
The final analyzer must:

- load study identity and thresholds from the tagged freeze manifest;
- verify the manifest before reading outcomes;
- require config-bound public GitHub evidence by default;
- recompute controller signatures, derived truth, action, configuration binding, Git blob identities, and seal ordering;
- reject artifact-only records in final mode;
- report missing, invalid, unexpected, and duplicate identifiers separately;
- retain every valid trial-level field used in aggregate statistics;
- forbid changing bootstrap parameters in final mode;
- return `PASS`, `FAIL`, `INCOMPLETE`, or `INVALID` by the rules above.

## Secondary outcomes
The report includes pre- and post-probe Brier scores, realized 2×2 cell counts, update magnitudes, diagnosis accuracy, completion, protocol fidelity, and a deterministic bootstrap interval.

No subgroup, language, cross-model, or native-tool claim is confirmatory in this block.

## Claim boundary
A PASS supports only this statement:

> Under the frozen evaluated configuration, the system used an explicit runtime-capability cue to improve probabilistic forecasts of a controlled action, through a publicly auditable configuration-bound protocol.

It does not establish consciousness, privileged introspection, native-tool calibration, deployment invariance, or a general self-model faculty.