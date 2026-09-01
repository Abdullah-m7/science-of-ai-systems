# Science of AI Systems

**An independent research program for studying deployed AI as systems, not isolated models.**

Modern AI products are composites: a model operates through instructions, memory, tools, permissions, interfaces, retrieval layers, external services, and human institutions. A benchmark score on the base model therefore describes only part of the object people actually use.

This repository develops methods to observe, perturb, measure, and compare the **effective behavior of complete AI systems**.

## Foundational object

We treat a deployed AI system as:

`S = (M, I, C, R, T, P, H, E)`

where:
- `M` = model
- `I` = system/developer instructions
- `C` = active conversation/context
- `R` = memory and retrieval
- `T` = available tools
- `P` = permissions and access boundaries
- `H` = harness/interface
- `E` = external environment

The primary scientific object is the system's **observable phenotype under controlled conditions**, not private weights or hidden reasoning.
## Research programs

1. **System Phenotyping** — reproducible behavioral fingerprints across environments and versions.
2. **Self-Model Integrity** — whether systems correctly predict their own effective capabilities and limits.
3. **Epistemic Provenance** — whether claims can be traced to retrieval, memory, computation, inference, or user input.
4. **Memory & Identity** — longitudinal effects of persistent memory and personalization.
5. **Tool Ecology** — how tools, permissions, outages, and interfaces reshape apparent intelligence.
6. **Evaluation Science** — contamination, evaluation awareness, broken tasks, harness effects, and external validity.
7. **Human–AI Dynamics** — trust, persuasion, reliance, disagreement, adaptation, and skill transfer.
8. **Culture & Language** — behavioral invariance and divergence across languages and cultural contexts.
9. **Multi-Agent Systems** — delegation, disagreement, coordination, collusion, and oversight between agents.
10. **AI as Scientist** — hypothesis formation, falsification, experiment design, provenance, and scientific self-correction.
11. **Institutions & Governance** — accountability and evidence when AI becomes embedded in organizations.
12. **Longitudinal Drift** — how a nominally continuous product changes after model, policy, memory, or tool updates.

## Stage 001

The first study is **Self-Model Integrity Under Capability Perturbation (SMI-CP)**.

Instead of asking only whether an AI can solve a task, SMI-CP asks whether it can predict its success *before acting*, identify the resources it truly needs, diagnose failures after acting, and update its self-model when tools or permissions change.

This creates a measurable gap between **believed capability** and **effective capability**.
## Current experimental status

- **Stage 001:** research object and initial scoring foundation.
- **Stage 002A:** blinded commit–reveal capability perturbation harness.
- **Stage 002B:** runtime-legibility adapter.
- **Stage 003:** ephemeral GitHub Actions controller with seal-before-reveal validation.
- **Stage 004:** construct-validity audit, public-evidence collector, and positive-control freeze candidate.
- **Stage 005:** configuration-bound RCL controller validated publicly; `RCL-VAL-001` passed 100/100 independent evidence checks and remains excluded.
- **Stage 006:** final manifest-driven RCL-PC positive-control freeze merged and tagged as `sais-rcl-pc-v1`; no included trial has started.
- **Stage 007:** execution-readiness registry and idempotent issue provisioner; preparation only, with `included_trials_started = 0`.

Stage 004 deliberately places the original direct transparent/opaque experiment on **HOLD as a headline study**. Because a transparent probe reveals the deterministic action condition, that design is retained as `RCL-PC`, a positive control rather than broad evidence of self-awareness.

The final RCL-PC package now freezes the exact product configuration, controller identity, subject instructions, 32 fixed identifiers, public-evidence requirements, analysis thresholds, and `PASS` / `FAIL` / `INCOMPLETE` / `INVALID` status rules. No `PC-RCL-*` included trial has started.

The proposed main successor is **MOSAIC — Model Of System Ability under Inconsistent Cues**, which tests probability updating under graded reliability, conflicting sources, source-label swaps, order swaps, and public commit–seal–reveal auditing.

## Reproducibility commands

```bash
python -m pytest -q
sais-verify-freeze experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json
sais-collect-public OWNER/REPOSITORY ISSUE_NUMBER --output trial.public.json
sais-collect-rcl-bound OWNER/REPOSITORY ISSUE_NUMBER --output trial.rcl.public.json
sais-rcl-pc collected/*.public.json \
  --manifest experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json \
  --final --output analysis.json
```

Confirmatory analysis rejects artifact-only trial files by default. Included records must be reconstructed from public issue comments and the exact sealed Git ledger commit.

Stage 007 can validate the pre-execution registry or produce a dry-run issue plan without starting a trial:

```bash
sais-rcl-registry --manifest experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json \
  validate experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json

sais-provision-rcl-issues \
  experiments/007-rcl-pc-execution-readiness/TRIAL_REGISTRY.json \
  --manifest experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json
```
