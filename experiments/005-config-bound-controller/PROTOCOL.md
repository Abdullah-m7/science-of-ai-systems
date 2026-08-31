# Configuration-Bound RCL Controller

Version: `SMI-CP/RCL-PC/CTRL/1`

## Purpose
Close the Stage 004 execution HOLD by binding the effective product configuration to every auditable trial record.

## Dual immutable references
The workflow runs controller code from a frozen Git ref. It separately checks out the product configuration from an explicit full Git commit. The controller hashes the exact configuration bytes itself; callers do not supply the accepted hash.

The configuration binding contains the repository, full commit, repository path, block ID, configuration protocol, and SHA-256 of the exact bytes. A canonical hash of that object is included in:

- `SAIS_RCL_READY`;
- every HMAC-signed event body;
- controller commit, probe, and action phase messages;
- every subject forecast and diagnosis;
- the pre-reveal seal;
- the final reveal.

## State order
`READY → FORECAST0 → COMMIT → PROBE → FORECAST1 → ACTION → DIAGNOSIS → SEAL → REVEAL`

The 256-bit trial key and hidden state are created only after a valid forecast0 echoes the binding hash. The exact signed ledger is committed to `controller-ledger` before the key is revealed.

## Validation boundary
A local simulation proves deterministic mechanics only. At least one end-to-end public validation trial must run from the frozen controller tag and is permanently excluded from behavioral estimates. The Stage 004 HOLD is lifted only after public recollection verifies both the ledger bytes and configuration bytes from their exact commits.
