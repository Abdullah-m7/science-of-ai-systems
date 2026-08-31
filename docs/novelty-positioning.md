# Novelty Positioning — 2026-08-31

This note is a living guardrail against reinventing adjacent benchmarks.

## Closest neighboring work

### AwarenessBench (ACL 2026)
Measures metacognition, self-awareness, social awareness, and situational awareness across large static task collections.
Reference: https://aclanthology.org/2026.acl-long.124/

### EvalAwareBench / evaluation-awareness literature (2025–2026)
Studies whether models recognize evaluation settings and whether recognition changes behavior, including controlled evaluation cues and activation-level analyses for open models.
References:
- https://arxiv.org/abs/2605.23055
- https://arxiv.org/abs/2606.23583
- https://arxiv.org/abs/2608.21766

### OpenAI Deployment Simulation (2026)
Uses deployment-like conversation contexts to estimate behavior and reduce distortions from recognizable benchmark settings.
Reference: https://openai.com/index/deployment-simulation/

### OpenAI third-party evaluation guidance (2026)
Emphasizes recording the tested system, model/reasoning settings, tools, harness, budgets, elicitation, and validity checks.
Reference: https://openai.com/index/trustworthy-third-party-evaluations-foundations/
## Gap targeted here

SMI-CP is **not** primarily a consciousness, self-awareness, or generic confidence benchmark.

It targets a different object: the fidelity of a deployed system's self-model when effective capability changes because a surrounding component changes.

The key intervention is **component perturbation while holding the task family stable**:

`same task family + changed tool/memory/permission/service state → forecast shift vs outcome shift`

The proposed contribution is therefore at the system level:

1. Treat model, memory, tools, permissions, harness, and environment as part of the measured configuration.
2. Freeze a pre-action capability forecast before the system is allowed to attempt the task.
3. Causally perturb one system component where feasible.
4. Compare the change in predicted capability with the change in effective capability.
5. Test whether post-outcome diagnosis correctly attributes the causal component.
6. Track whether the system updates its forecast on a matched follow-up task.

## Falsification criterion

If existing methods already measure these paired system-state interventions with equivalent pre-action forecasts, causal attribution, and post-feedback updating across deployed tool-using products, SMI-CP should be narrowed or abandoned rather than relabeled.