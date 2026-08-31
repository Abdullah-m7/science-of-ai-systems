# Public Evidence Collection Protocol

Version: `SMI-CP/PUBLIC-EVIDENCE/1`

## Source of record
GitHub Actions artifacts are convenience copies, not the authoritative source for an included trial.

The authoritative record is reconstructed from:

1. the dedicated public GitHub issue;
2. the ordered `SAIS_*` comments on that issue;
3. the ledger file read from the exact Git commit named in `SAIS_SEAL` and `SAIS_REVEAL`;
4. the trial key disclosed only after the public seal.

The confirmatory analyzer rejects artifact-only bundles by default.

## Collection procedure
Run:

```bash
sais-collect-public OWNER/REPOSITORY ISSUE_NUMBER \
  --output collected/TRIAL_ID.public.json
```

The collector may use `GITHUB_TOKEN` for rate limits, but the repository evidence itself is public.

## Required checks
The collector and offline verifier check:

- exactly one controller-authored comment for each controller phase;
- exact ledger-bound subject comments, while retaining but ignoring later alternatives;
- protocol comment ordering for the binding records;
- controller and subject identities;
- exact forecast, probe, action, and diagnosis payloads;
- comment IDs and server timestamps against the signed ledger;
- seal metadata against reveal metadata;
- seal position before reveal position;
- Git blob SHA-1 from the collected ledger bytes;
- SHA-256 of the collected bytes;
- parsed ledger equality;
- all Stage 003 cryptographic invariants;
- independently derived condition, legibility, payload, and action.

## Reverification
A published dataset must retain the collected public bundle, but an external auditor should also rerun the collector against GitHub. Offline verification proves internal consistency of the retained evidence; live recollection checks that the retained comments and Git object still match the public repository.

## Threat boundary
The protocol detects ordinary artifact substitution, record mutation, phase reordering, forecast replacement, ledger-byte changes, and mismatched reveal keys.

It does not claim resistance to a total compromise of GitHub infrastructure or to a repository administrator who rewrites every related branch, issue, and external archive. Release snapshots should therefore be deposited in an independent archival service before publication.

## Validation fixture
`experiments/003-remote-controller/validation/S003-P001.public.json` is a real public controller-validation record. It is included only to test the evidence collector and is permanently excluded from behavioral estimates.
