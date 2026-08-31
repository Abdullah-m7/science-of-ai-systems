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