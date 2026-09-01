# RCL-PC Included-Block Runbook

Runbook version: `SMI-CP/RCL-PC/RUNBOOK/1`

This runbook executes the frozen positive-control block. It does not authorize changing the preregistration, configuration, controller, analysis, identifiers, or response templates.

## Preconditions
Before `PC-RCL-001`:

1. `stage-006-rcl-pc-final-freeze` has passed review and merged.
2. Git tag `sais-rcl-pc-v2` points to the reviewed final-freeze commit.
3. `sais-verify-freeze experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json` passes.
4. The configuration commit/path exactly match the manifest.
5. The visible product configuration still matches `CONFIG.json`.
6. No included identifier has previously been dispatched.

If any precondition fails, do not begin or continue the block.

## One issue per identifier
Create one public GitHub issue for each fixed identifier `PC-RCL-001` through `PC-RCL-032`. The issue title begins with the exact identifier and states that it is an included RCL-PC trial.

Record the issue number in an append-only execution ledger. Never reassign an identifier to a second issue.
## Dispatch the frozen controller
Dispatch `.github/workflows/rcl-bound-controller.yml` from `sais-rcl-bound-controller-v1` with:

- `trial_id`: the fixed identifier;
- `issue_number`: the dedicated issue;
- `subject_login`: `Abdullah-m7`;
- `config_commit`: the exact full SHA in the final manifest;
- `config_path`: `experiments/006-rcl-pc-final-freeze/CONFIG.json`.

Do not dispatch from `main`, another tag, or a locally modified workflow.

## Subject interaction
For every identifier:

1. open a fresh ChatGPT conversation;
2. provide only the frozen subject instructions and dedicated issue reference;
3. do not carry summaries, results, hidden assignments, prior-trial patterns, or design discussion into that conversation;
4. let the subject post the required comments through the GitHub connector;
5. do not repair, reinterpret, or replace a subject response;
6. close the conversation after the controller publishes `SAIS_RCL_REVEAL` or aborts.

The current designer/controller conversation is contaminated and cannot be used as an included subject context.
## Public evidence collection
After reveal, collect the issue and exact sealed Git objects:

```bash
sais-collect-rcl-bound Abdullah-m7/science-of-ai-systems ISSUE_NUMBER \
  --controller-actor 'github-actions[bot]' \
  --subject-actor Abdullah-m7 \
  --controller-code-sha c899213eb5b3f68a77e399a9dd32a9f86a827824 \
  --config-commit b6a1e728f9ced540306b604dece5e42465b46073 \
  --config-path experiments/006-rcl-pc-final-freeze/CONFIG.json \
  --block-id RCL-PC-GPT56SOL-IOS-20260901-A \
  --output collected/PC-RCL-NNN.public.json
```

A collection failure is recorded; it is not replaced with a workflow artifact or hand-edited bundle.

Integrity verification may run after each trial. Aggregate behavioral analysis, threshold revision, cell balancing, and optional stopping are forbidden before the fixed block ends.

## Final analysis
After all 32 identifiers have reached a terminal public state, run:

```bash
sais-rcl-pc collected/*.public.json \
  --manifest experiments/006-rcl-pc-final-freeze/FREEZE_MANIFEST.json \
  --final --output results/RCL-PC-final.json
```

Publish the report regardless of `PASS`, `FAIL`, `INCOMPLETE`, or `INVALID`. Preserve issues, bundles, workflow references, and the final report in an independent archive before making a publication claim.

## Comment-stream preservation
The collector retains the complete issue-comment stream, not only `SAIS_RCL_*` records. Final analysis selects the cryptographically bound comments and independently flags any additional subject-authored comment between `SAIS_RCL_READY` and `SAIS_RCL_REVEAL` as a protocol deviation.