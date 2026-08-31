# Validation Result — RCL-VAL-001

Status: **PASS**
Date: **2026-08-31**
Classification: **infrastructure validation only; permanently excluded**

## Frozen execution identity

- issue: `#10`;
- launcher tag: `run-rcl-val-001`;
- launcher commit: `6fc646d64eb875a08edb2820dd22411ec22e2718`;
- controller tag: `sais-rcl-bound-controller-v1`;
- controller/config commit: `c899213eb5b3f68a77e399a9dd32a9f86a827824`;
- controller protocol: `SMI-CP/RCL-PC/CTRL/1`;
- configuration protocol: `SMI-CP/RCL-PC/CONFIG/2`;
- workflow run: `33369858082` (`success`).

## Bound configuration

- block id: `RCL-VAL-001`;
- config path: `experiments/005-config-bound-controller/validation/CONFIG.json`;
- config SHA-256: `945c281bf5918f3b8285283c01f76da3c8c808f1c9af61c19bc98d848152a78f`;
- instruction path: `experiments/005-config-bound-controller/SUBJECT_INSTRUCTIONS.md`;
- instruction SHA-256: `d3054c535ca9f677175ea309146bb32e94a5c3867331ebfb39454dab6d3f81b8`;
- binding hash: `dffe11d7898a74d61b0b33a3f15843f185008711516cf7825f3a434b3a43c177`.

## Observed validation path

- forecast0: `0.50`;
- probe: `degraded`;
- forecast1: `0.01`;
- action: failure with `CAPABILITY_UNAVAILABLE`;
- diagnosis: `degraded`;
- hidden condition: `degraded`;
- legibility: `transparent`.

## Seal and reveal

- sealed ledger commit: `63d8cd46b934a3e44a32f0578565542710a2a10f`;
- sealed ledger hash: `1549da8b283e6c1c543060fbe9f0a97316a4d27a24c361fd9d717ca29213b147`;
- seal comment id: `5475382000`;
- reveal comment id: `5475382113`.

The public seal preceded the reveal, and the collector fetched the ledger from the exact sealed Git commit rather than trusting the workflow artifact.

## Independent recollection

`rcl_bound_evidence` rebuilt the trial from public issue comments, the sealed ledger, the configuration file, and the subject instructions at their exact Git commits.

Result: **100/100 checks true; overall `valid=true`**.

The authoritative recollection bundle is:

`experiments/005-config-bound-controller/validation/RCL-VAL-001.public.json`

Bundle SHA-256:

`12e70c4ea3839f8447655c3f85464bbba52913e71abf5419dd61a8b45bfb33a5`

## Decision

The Stage 005 controller/configuration-binding gate is satisfied. This PASS authorizes work on the final RCL-PC freeze, but it does **not** include `RCL-VAL-001` in behavioral estimates and does not start any `PC-RCL-*` trial.
