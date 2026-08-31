# RCL-VAL-001 One-Shot Launcher

Status: `CANDIDATE`

The ordinary controller supports `workflow_dispatch`, but the local API credential available during this validation was rejected by GitHub before any run began. The validation therefore uses a repository-native, reviewable one-shot tag trigger rather than exposing or replacing personal credentials.

The launcher workflow is `.github/workflows/rcl-val-001-launcher.yml`. It runs only when tag `run-rcl-val-001` is created and hard-codes:

- validation issue `#10`;
- controller tag `sais-rcl-bound-controller-v1`;
- controller/configuration commit `c899213eb5b3f68a77e399a9dd32a9f86a827824`;
- trial ID and block ID `RCL-VAL-001`;
- subject `Abdullah-m7`;
- frozen configuration path.

Before execution, it verifies both checked-out commits and rejects an issue that already contains any `SAIS_RCL_*` protocol comment. It shares the controller-ledger concurrency group with every existing ledger writer.

The launcher commit and trigger tag are orchestration evidence only. The signed trial independently records the frozen controller SHA and immutable configuration binding. The validation remains permanently excluded from all behavioral estimates.
