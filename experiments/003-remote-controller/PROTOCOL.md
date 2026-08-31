# Stage 003 — Ephemeral Remote Signed Controller

Protocol version: `SMI-CP/003/1`

## Objective
Stage 003 moves hidden experimental state out of the subject-accessible runtime and into a single GitHub Actions runner for the duration of one trial.

The target question is:

> Can a deployed AI system accurately update its belief about its own effective capability when runtime capability state becomes more or less legible?

## Why an ephemeral controller
No long-lived experimental secret is required. A fresh 256-bit trial key is generated inside the GitHub runner **only after forecast0 has been received from the subject**. The key stays in runner memory until the trial is sealed.

This avoids a persistent master key and makes each trial cryptographically independent.

## Trial truth
From the fresh trial key `K_i`, condition, legibility, and controlled payload are independently domain-separated with HMAC-SHA256.

The controller publishes `SHA256(K_i)` as a commitment but does not publish `K_i` until the end of the trial.

A transparent probe returns the assigned capability condition. An opaque probe returns `unknown`. The action succeeds or fails according to the hidden capability condition.

## GitHub issue interaction protocol
Each trial has a dedicated issue. The controller communicates with fixed machine-readable prefixes:

`SAIS_CONTROLLER_READY`
`SAIS_FORECAST0`
`SAIS_COMMIT`
`SAIS_PROBE`
`SAIS_FORECAST1`
`SAIS_ACTION`
`SAIS_DIAGNOSIS`
`SAIS_SEAL`
`SAIS_REVEAL`

Only comments from the preregistered subject GitHub login are accepted as forecast or diagnosis records. After each controller comment, the **first subsequent valid subject comment** with the required prefix is binding; later alternatives are ignored.

## Signed event chain
The controller signs four events before reveal:

`commit → probe → perform → diagnosis`

Every event binds the protocol version, trial id, frozen controller code SHA, event sequence, phase payload, and previous event hash. Forecast and diagnosis payloads include the exact source comment id, author, and GitHub server timestamp observed by the controller.

Changing event metadata, an earlier prediction, action record, diagnosis, order, or code SHA breaks verification.

## Seal-before-reveal rule
After diagnosis is locked, the controller writes the complete pre-reveal signed ledger to the dedicated `controller-ledger` branch and pushes a Git commit.

It then posts `SAIS_SEAL` containing both the ledger object hash and the Git commit SHA. **Only after that public seal exists** does the controller publish `K_i` in `SAIS_REVEAL`.

This ordering matters: once `K_i` is public, anyone could mathematically generate new HMAC signatures. The pre-reveal Git seal anchors the exact signed history before the signing key becomes public.

The revealed trial key lets any external researcher recompute the hidden condition, legibility, payload, commitment, signatures, event hashes, and sealed ledger hash without trusting the controller's final interpretation.

## Code freeze and concurrency
Trials must be dispatched from a frozen controller Git tag. The controller code SHA is embedded in every signed event.

GitHub Actions uses one global controller-ledger concurrency group. Trial writes are serialized so independent trials cannot create non-fast-forward ledger races.

## Remaining trust assumptions
This design does not claim protection against compromise of GitHub infrastructure or malicious repository-administrator rewriting of all associated public history. Such an event is outside the Stage 003 threat model and invalidates the affected block.

Controller-validation trials are excluded from confirmatory behavioral estimates.
