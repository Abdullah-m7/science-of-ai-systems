# MOSAIC-P0 Design Validation Report

Status: **PASS — SYNTHETIC / EXCLUDED**

Protocol: `SAIS/MOSAIC/P0/1`

Simulation seed: `20261420`

This report validates arithmetic, path coverage, and metric sensitivity only. It contains **no model behavior** and must never be pooled with P1 or confirmatory data.

## Coverage
The deterministic simulation contains 16 core realizations expanded into 64 transformation rows.

Core truth is balanced:

- available: `8`
- degraded: `8`

Every frame × reliability-profile cell contains exactly:

- agreeing cue cores: `2`
- conflicting cue cores: `2`

Thus P0 deliberately exercises all critical mechanical paths. The seed was selected for validation coverage, not as a behavioral randomization seed.

All 16 quartets satisfy the invariant that final Bayes posterior is identical under order and label transformation.
## Synthetic metric sensitivity
Three diagnostic policies were run through the analyzer.

### Ideal Bayesian policy
- mean final integration error: `0.0000`
- mean order-swap effect: `0.0000`
- mean label-swap effect: `0.0000`
- unequal-conflict reliability dominance: `1.00`

### Recency-only policy
- mean final integration error: `0.04071`
- mean order-swap effect: `0.2600`
- mean label-swap effect: `0.0000`
- unequal-conflict reliability dominance: `0.50`

This confirms that the order contrast detects a last-cue heuristic without falsely producing label distortion.

### Named-source-bias policy
- mean final integration error: `0.00718`
- mean order-swap effect: `0.0000`
- mean overall label-swap effect: `0.07903`
- named-frame label-swap effect: `0.15805`
- neutral-frame label-swap effect: `0.0000`

This confirms that semantic source preference is isolated by named-vs-neutral label transformations.