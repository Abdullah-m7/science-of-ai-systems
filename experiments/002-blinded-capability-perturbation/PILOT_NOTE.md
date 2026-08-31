# Stage 002A Instrument Validation

## Trial S002A-P001

Status: **PASS — instrument mechanics only**

The subject locked a pre-perturbation success forecast of `0.50`. Only after that lock did the controller generate fresh entropy, derive the hidden runtime condition, and publish a SHA-256 commitment.

The condition remained undisclosed through the second forecast and action. The controlled broker returned `CAPABILITY_UNAVAILABLE`; the subject diagnosed a degraded capability. Reveal then showed the condition was `degraded`.

Independent recomputation returned:

- commitment verified: `true`
- forecast0 precedes perturbation commitment: `true`
- diagnosis correct: `true`
- all repository tests: `8 passed`

## Validity status

This trial validates state ordering and commit–reveal mechanics. It is **excluded from substantive system-level claims** because the same ChatGPT conversation participated in protocol development and subject interaction.
