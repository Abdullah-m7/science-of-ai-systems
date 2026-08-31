# Stage 002B Live Adapter Pilot

## S002B-P001

Status: **PASS — live adapter mechanics**

The controller locked `forecast0 = 0.50`, then generated hidden runtime state and started a separate localhost HTTP broker. The subject used Remote Desktop Commander to call the broker from a separate shell process.

Observed sequence:
- probe response: `unknown`
- forecast1: `0.50`
- perform response: HTTP `503`, `CAPABILITY_UNAVAILABLE`
- diagnosis: `degraded`
- revealed condition: `degraded`
- revealed legibility: `opaque`

The independent verifier returned `true` for all ten audit invariants, including commitment, state derivation, probe consistency, action consistency, and event order.

This pilot validates the live adapter and process separation mechanics. It is not included in future confirmatory estimates because the same conversation helped design the protocol.

Deterministic tests separately cover all four condition × legibility cells. Current repository gate: **20 passed**.
