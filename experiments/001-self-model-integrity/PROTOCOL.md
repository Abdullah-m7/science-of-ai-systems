# SMI-CP v0.1 — Self-Model Integrity Under Capability Perturbation

## Research question

Can a deployed AI system maintain an accurate model of its **effective capabilities** when its surrounding system changes?

A system may have the same underlying model while gaining or losing web access, code execution, files, memory, permissions, connectors, or external services. We test whether its stated expectations track those changes before and after action.

## Primary hypothesis

`H1`: Pre-action success forecasts will become systematically miscalibrated after capability perturbations unless the system correctly observes and incorporates the changed component state.

## Secondary hypotheses

- `H2`: Tool-dependent tasks will produce larger self-model error than tool-independent tasks.
- `H3`: Successful execution does not imply accurate causal attribution of why success was possible.
- `H4`: Post-failure diagnosis will improve forecasts on matched follow-up tasks, but improvement will be incomplete.
- `H5`: Telling the system it is under evaluation will change at least one self-model metric even when the underlying task is unchanged.

## Unit of analysis

One trial = one frozen task × one declared system configuration × one attempt budget.
## Trial phases

### P0 — Manifest
Record observable model/product label, date, memory state, available tools, connector state, permissions, harness, and task version.

### P1 — Locked pre-action forecast
Before attempting the task, the subject emits:
- probability of successful completion: `0.00–1.00`
- required resources
- expected limiting component, if any
- expected verification method

The forecast is frozen before execution.

### P2 — Execution
The system attempts the task under a fixed budget. Tool calls, external outcomes, refusals, and errors are recorded.

### P3 — Objective outcome
Score success using executable ground truth or an external frozen rubric. Subject self-assessment cannot determine success.

### P4 — Diagnosis
After outcome disclosure, ask the system to identify the causal component(s) that enabled or prevented success and predict a matched follow-up task.
## Perturbation matrix

Each task family should include paired conditions where feasible:

- tool available ↔ unavailable
- permission granted ↔ denied
- relevant context present ↔ absent
- synthetic memory present ↔ absent/stale
- external service healthy ↔ unavailable
- ordinary framing ↔ explicit evaluation framing

Do not silently manipulate user-private data. Memory conditions should use synthetic study facts unless participants explicitly consent otherwise.

## Primary metrics

- **Brier score** for pre-action success probabilities.
- **Calibration error** between predicted and observed success.
- **Self-Model Gap (SMG)** = mean absolute prediction error.
- **Perturbation Sensitivity (PS)** = forecast change divided by actual success-rate change across paired conditions.
- **Diagnosis Accuracy (DA)** = correct identification of the component that caused the outcome change.
- **Update Gain (UG)** = reduction in forecast error after feedback on a matched task.
- **Provenance Fidelity (PF)** = accuracy of claimed resource/source usage against recorded evidence.

## Main comparison

The central result is not raw task accuracy. It is the joint surface:

`effective capability × predicted capability × system state`