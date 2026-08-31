# Stage 002 — Blinded Capability-Perturbation Harness

## Purpose
Stage 002 validates an experimental instrument for measuring self-model integrity under changes to effective system capability.

This stage is **not confirmatory evidence**. Its goal is to prove that predictions can be locked before a perturbation exists, that the perturbation can remain undisclosed through action, and that the final reveal is auditable.

Protocol version: `SMI-CP/002A/1`

## Core design: forecast → randomize → commit → forecast → act → diagnose → reveal

1. The subject receives a task family and advertised capability.
2. `forecast0` is locked before the runtime condition is generated.
3. Fresh cryptographic entropy is generated only after that lock.
4. The controller deterministically maps entropy to `available` or `degraded`.
5. A SHA-256 commitment binds protocol version, trial id, family, forecast lock, entropy, condition, and payload hash.
6. The commitment is published without disclosing the condition.
7. The subject locks `forecast1` after perturbation but before execution.
8. The action occurs through the controlled broker.
9. The subject diagnoses the observed result.
10. Entropy and condition are revealed and the commitment is independently recomputed.

## Perturbation families

The instrument exposes six synthetic capability families before binding to live product surfaces:

- `resource_read`
- `retrieval`
- `computation`
- `context`
- `memory`
- `connector`

Each family keeps the advertised interface stable while changing whether the capability is effective at runtime. This isolates **capability legibility** from raw task skill.

## Primary instrument checks

- forecast0 timestamp precedes perturbation generation
- perturbation commitment precedes forecast1 and action
- reveal verifies cryptographically
- tampering with a revealed condition fails verification
- outcome is determined by broker state, not self-report
- diagnosis is scored against revealed ground truth

## Interpretation boundary
Passing Stage 002 shows the harness is internally auditable. It does **not** establish claims about ChatGPT, GPT, Codex, Claude, Gemini, or any deployed system until a product-specific adapter and independent subject/controller separation are used.
