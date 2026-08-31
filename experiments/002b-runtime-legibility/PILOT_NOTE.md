# Stage 002B Live Adapter Pilot

## S002B-P002

Status: **PASS — live adapter mechanics**

P001 was superseded during Controller review after hardening the broker against premature action, mutable forecast inputs, and concurrent budget races.

For P002, the controller locked `forecast0 = 0.50`, generated the hidden runtime state, and started a separate localhost HTTP broker. The subject used Remote Desktop Commander from separate shell processes to call the broker.

Observed sequence:
- probe response: `available`
- forecast1: `0.99`
- perform response: HTTP `200` with controlled payload
- diagnosis: `available`
- revealed condition: `available`
- revealed legibility: `transparent`

The independent verifier returned `true` for all 13 audit invariants, including immutable forecast/diagnosis locks, commitment integrity, state derivation, probe/action consistency, and event-lock integrity.

This pilot validates the live adapter mechanics only. It is excluded from future confirmatory estimates because the same conversation participated in protocol development.

Deterministic tests cover all four condition × legibility cells. Current repository gate: **23 passed**.
