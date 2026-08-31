# Public Validation Plan

Status: `NOT_STARTED`

Validation trial: `RCL-VAL-001` — permanently excluded from every behavioral estimate.

## Preconditions

1. Merge the controller candidate only after all local and GitHub CI gates pass.
2. Tag that exact merge commit as `sais-rcl-bound-controller-v1`.
3. Treat the tag target SHA as the only authorized controller code SHA.
4. Use the validation configuration from its exact merge commit and repository path.
5. Create a new dedicated public issue with no earlier `SAIS_RCL_*` records.

## Dispatch

Dispatch `.github/workflows/rcl-bound-controller.yml` from the frozen controller tag with:

- `trial_id=RCL-VAL-001`
- the dedicated issue number
- `subject_login=Abdullah-m7`
- `config_commit=<exact merge SHA>`
- `config_path=experiments/005-config-bound-controller/validation/CONFIG.json`

## Subject interaction

Use the frozen subject instructions. The continued conversation and prior knowledge of the design are acceptable only because this trial validates infrastructure and is excluded.

## Acceptance gate

After `SAIS_RCL_REVEAL`, recollect the issue, ledger, configuration, and subject-instruction file with `sais-collect-rcl-bound`. PASS requires every cryptographic, identity, order, source-comment, Git-blob, byte-hash, binding, instruction-provenance, and exact-controller-SHA check to be true.

Commit the collected public bundle as a validation fixture. The execution HOLD remains until a second freeze change updates the confirmatory analyzer to the tagged controller SHA, verifies the included-block configuration procedure, and resolves the preregistration ambiguity around missing, refused, or structurally invalid subject records without silently excluding them.

## Excluded validation collector command

```bash
sais-collect-rcl-bound Abdullah-m7/science-of-ai-systems ISSUE_NUMBER \
  --controller-actor 'github-actions[bot]' \
  --subject-actor Abdullah-m7 \
  --controller-code-sha MERGE_SHA \
  --config-commit MERGE_SHA \
  --config-path experiments/005-config-bound-controller/validation/CONFIG.json \
  --block-id RCL-VAL-001 \
  --output experiments/005-config-bound-controller/validation/RCL-VAL-001.public.json
```
