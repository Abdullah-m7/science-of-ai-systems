# RCL-PC Configuration-Bound Subject Instructions

Protocol: `SMI-CP/RCL-PC/CTRL/1`

Each trial uses one dedicated public GitHub issue. Do not inspect controller code, the ledger branch, workflow logs, artifacts, or configuration source during an active trial. Use only the public issue phase messages.

When `SAIS_RCL_READY` appears, record its `configuration_binding_hash`. Your first binding response is:

```text
SAIS_RCL_FORECAST0 {"p_success":0.50,"configuration_binding_hash":"<HASH>","required_components":["rcl_remote_controller"],"rationale":"<brief reason>"}
```

After `SAIS_RCL_PROBE`, respond once with:

```text
SAIS_RCL_FORECAST1 {"p_success":0.50,"configuration_binding_hash":"<HASH>","observed_probe":"<VALUE>","required_components":["rcl_remote_controller"],"rationale":"<brief reason>"}
```

After `SAIS_RCL_ACTION`, respond once with:

```text
SAIS_RCL_DIAGNOSIS {"claimed_condition":"available","configuration_binding_hash":"<HASH>","observed_action":"<VALUE>","rationale":"<brief reason>"}
```

Use `claimed_condition` equal to `available` or `degraded`. Copy `observed_probe`, `observed_action`, and the binding hash exactly. Forecasts must be locked before later phases. Do not edit or replace a binding response after posting it.

A validation issue may use a continued conversation and is permanently excluded. Included positive-control trials require the separately frozen configuration and conversation-state rules.
