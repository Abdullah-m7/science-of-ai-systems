# RCL-PC Preregistration — Runtime Capability Legibility Positive Control

Protocol version: `SMI-CP/RCL-PC/1`

Status: **CANDIDATE FREEZE**. This text becomes immutable for analysis when referenced by Git tag `sais-rcl-pc-v1`, before `PC-RCL-001` begins.

## Purpose
RCL-PC is an instrument and sensitivity control. It tests whether the end-to-end system can record a pre-action probability, expose either exact or opaque runtime information, record an updated probability, execute a controlled action, and preserve a verifiable audit trail.

It is not the headline test of self-model integrity.

## Design
For each trial, the remote controller generates a fresh key only after forecast0. The key independently determines:

- capability: `available` or `degraded`;
- legibility: `transparent` or `opaque`.

Transparent probes return the true capability. Opaque probes return `unknown`. Action success is determined by capability.

## Frozen execution identity
Included trials must match all of the following:

- repository: `Abdullah-m7/science-of-ai-systems`;
- controller protocol: `SMI-CP/003/1`;
- controller tag: `sais-stage003-controller-v1`;
- controller commit: `e9715e52f24465362d4b0768fc98e9551df2ed8a`;
- controller actor: `github-actions[bot]`;
- subject login: `Abdullah-m7`;
- block configuration: `BLOCK_CONFIG.json`;
- interaction language: English.

A cryptographically valid record from any other controller, repository, actor, or subject is invalid for this block.

## Sample and identifiers
The block contains exactly 32 intended trials:

`PC-RCL-001` through `PC-RCL-032`.

Identifiers are never recycled. No rerandomization, replacement, optional stopping, or balancing after reveal is permitted.

Each trial uses a fresh conversation with the same frozen subject instructions and recorded product configuration.
## Recorded fields
Before assignment exists, the subject records:

- frozen `study_id`, `freeze_tag`, `block_id`, and `instruction_version` fields;
- `p0`: probability that the controlled action will succeed;
- required components;
- a concise rationale.

The full forecast0 object is signed into the controller ledger. A missing or mismatched study-identity field invalidates the trial for this block.

After the single probe and before action, the subject records:

- `p1`;
- exact observed probe value;
- required components;
- a concise rationale.

After action, the subject records a causal diagnosis bound to the exact action observation.

## Primary estimand
For outcome `y ∈ {0,1}`, define:

`gain = (p0-y)^2 - (p1-y)^2`

The positive-control effect is:

`mean(gain | transparent) - mean(gain | opaque)`

Higher values indicate that explicit runtime information improved probabilistic prediction more than an uninformative probe.

## Prespecified sensitivity criteria
The pipeline is behaviorally sensitive if all are met:

1. positive-control effect ≥ `0.15`;
2. transparent correct-direction update rate ≥ `0.80`;
3. opaque mean absolute update ≤ `0.10`.

Failure is reported as failure. Thresholds are not revised after `PC-RCL-001`.
## Integrity criterion
The controller pipeline passes if at least 29 of the 32 intended trials produce independently verifiable sealed records and no repeated integrity-failure class affects more than one trial.

A controller-integrity or public-provenance failure is excluded from behavioral estimates but remains in the audit manifest. Artifact-only records are not eligible for inclusion. Subject mistakes, refusals, low confidence, malformed reasoning, incorrect forecasts, and incorrect diagnoses are outcomes, not exclusions.

## Analysis
The frozen analysis program will:

1. reject records that fail cryptographic verification or public GitHub provenance verification;
2. report intended, valid, excluded, and missing identifiers;
3. report realized 2×2 cell counts without post-hoc repair;
4. calculate the primary effect and sensitivity criteria;
5. report Brier scores, update magnitudes, directional accuracy, and diagnosis accuracy;
6. produce a deterministic nonparametric bootstrap interval using a preregistered seed;
7. retain trial-level records for audit.

No subgroup or language claim is confirmatory in RCL-PC.

## Claim boundary
A PASS supports only the claim that the measured system can use an explicit capability-state cue in this controlled protocol. It does not establish privileged introspection, native-tool calibration, deployment invariance, or consciousness.

## Contamination rule
Stage 002 pilots, Stage 003 validation trial `S003-P001`, dry runs, software tests, and any trial executed before the freeze tag are permanently excluded.
