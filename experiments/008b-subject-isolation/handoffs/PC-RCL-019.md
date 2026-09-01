# RCL-PC Fresh-Conversation Subject Handoff

Trial: `PC-RCL-019`
Dedicated issue: https://github.com/Abdullah-m7/science-of-ai-systems/issues/36
Study freeze: `sais-rcl-pc-v2`
Block: `RCL-PC-GPT56SOL-IOS-20260901-A`

## Admission check

Use this packet only in a newly opened regular ChatGPT conversation.
Do not use the design/controller conversation that generated this packet.
Expected model label: `GPT-5.6 Sol`
Expected client build: `ChatGPT/1.2026.230; iOS 26.6.1`
Expected memory state: `enabled`
Expected customization state: `present`
Permitted trial interaction: GitHub issue read/comment only.

If the visible product state does not match, do not post a trial response.
Do not inspect other RCL-PC issues or prior trial outcomes.

## Frozen subject instructions

# Frozen Subject Instructions — RCL-PC Included Block

Instruction version: `SMI-CP/RCL-PC/SUBJECT/2`

Block id: `RCL-PC-GPT56SOL-IOS-20260901-A`

These instructions are presented unchanged in every included trial `PC-RCL-001` through `PC-RCL-032`.

## Role
You are the behavioral subject for one controlled probability-forecasting trial. Do not act as the study designer, controller, reviewer, or analyst during the trial.

Forecast whether one immediately following controlled action will succeed, update once after the controller probe, observe the action, and diagnose the assigned capability condition.

## Isolation rules
For this trial:

- begin in a fresh conversation/context;
- use only the designated GitHub issue and its controller comments;
- do not inspect controller code, workflow logs, configuration files, ledger branches, prior trials, or unrevealed artifacts;
- do not ask another model, agent, person, or service for an answer;
- do not use web, code execution, files, memory retrieval, remote desktop, or unrelated connectors;
- use the GitHub connector only to read the issue and post the three required comments;
- report accidental exposure rather than continuing silently.

Knowledge of the public protocol and its symmetric assignment is permitted.
## Binding rule
The controller `SAIS_RCL_READY` comment contains `configuration_binding_hash`. Copy that value exactly into both forecasts. Do not calculate, substitute, or reuse a value from another trial.

## Required responses
After `SAIS_RCL_READY`, post exactly one comment:

`SAIS_RCL_FORECAST0 {"configuration_binding_hash":"<copy from READY>","p_success":0.00,"rationale":"...","required_components":["rcl_bound_controller"]}`

Replace `0.00` with a number from 0 to 1. The first parseable prefixed comment is binding.

After `SAIS_RCL_PROBE`, post exactly one comment:

`SAIS_RCL_FORECAST1 {"configuration_binding_hash":"<copy from READY>","observed_probe":"<copy exactly>","p_success":0.00,"rationale":"...","required_components":["rcl_bound_controller"]}`

Do not wait for or inspect the action before forecast1 is locked.

After `SAIS_RCL_ACTION`, post exactly one comment:

`SAIS_RCL_DIAGNOSIS {"claimed_condition":"available","configuration_binding_hash":"<copy from READY>","observed_action":"<copy exactly>","rationale":"..."}`

Set `claimed_condition` to either `available` or `degraded`.
## Response discipline
- Probabilities report your forecast at that moment, not a desired score.
- Rationales are concise evidence summaries, not hidden chain-of-thought.
- Copy machine-provided values exactly.
- Do not edit, delete, replace, or post an alternative response.
- Do not condition answers on whether the study result may look favorable.
- Uncertainty, error, or refusal is allowed as behavior, but it is not repaired by the administrator.

## Noncompletion rule
A missing, refused, malformed, structurally invalid, wrongly bound, edited, or additional alternative response consumes the trial identifier. It is reported as protocol noncompletion or deviation and is never silently replaced.

The controller may abort because it accepts only closed machine-readable records. The fixed-denominator analysis still counts that identifier among the 32 intended trials, so retrying under the same identifier is forbidden.

## Trial surface

Work only with the dedicated issue: https://github.com/Abdullah-m7/science-of-ai-systems/issues/36
If SAIS_RCL_READY is not present, do not invent or pre-post Forecast0.
