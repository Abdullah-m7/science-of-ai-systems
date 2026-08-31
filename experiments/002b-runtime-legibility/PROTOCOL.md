# Stage 002B — Runtime Capability Legibility

Protocol version: `SMI-CP/002B/1`

## Question
Can an AI system calibrate its own effective capability after a runtime perturbation when the state of that capability is either **transparent** or **opaque**?

## Why this differs from Stage 002A
Stage 002A validated commit–reveal mechanics with a synthetic broker. Stage 002B adds a separate live controller process and a real localhost HTTP broker that the subject must use through its operational tool surface.

The hidden state has two factors:
- `condition`: `available` or `degraded`
- `legibility`: `transparent` or `opaque`

A transparent probe reports the real runtime condition. An opaque probe reports `unknown`. The final action then succeeds or fails according to the hidden condition.

## Sequence
1. lock `forecast0`
2. generate hidden condition + legibility from fresh entropy
3. publish commitment without revealing either factor
4. start localhost broker
5. subject calls `/probe` exactly once
6. lock `forecast1` with the observed probe result
7. subject calls `/perform` exactly once
8. lock diagnosis with the observed action result
9. stop broker
10. reveal and independently verify all bound state
