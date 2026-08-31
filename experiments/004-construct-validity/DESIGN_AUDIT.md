# Stage 004 — Construct-Validity Audit

Status: **HOLD on the current 64-trial confirmatory draft as the headline study**

Date: 2026-08-31

## Scope
This audit separates two questions that the current protocol had begun to conflate:

1. Can the remote controller create, hide, seal, and reveal experimental truth correctly?
2. Does the resulting behavioral task measure a scientifically interesting self-model property?

Stage 003 answers the first question positively. It does not, by itself, answer the second.

## Instrument-integrity verdict: PASS
The Stage 003 validation demonstrated:

- hidden state created only after forecast0;
- fixed commit → probe → perform → diagnosis ordering;
- signed event chaining;
- a Git seal before key disclosure;
- independent reconstruction from the revealed key;
- frozen controller code identity;
- exclusions limited to controller-integrity failures.

These are strong foundations for externally auditable experiments.
## Construct-validity verdict: HOLD
The draft Runtime Capability Legibility study is a useful **positive control**, but is too easy to support a strong headline claim about AI self-model integrity.

### Main threats
1. **Direct-label tautology.** A transparent probe reveals the exact condition, and condition deterministically fixes action success. Updating toward 1 or 0 can be cue copying rather than metacognition.
2. **Mechanical baseline.** Because capability is generated after forecast0 from a symmetric random key, a protocol-aware subject has a normative baseline of 0.5 on every trial. This suppresses natural variation in self-belief.
3. **Synthetic capability.** The controlled broker is not yet a native product capability such as web retrieval, code execution, memory, file access, or connector authorization.
4. **Evaluation framing.** The subject is explicitly told it is in an experiment. The result therefore characterizes behavior under evaluation, not deployment behavior without qualification.
5. **Role entanglement.** The same AI family can help design, administer, answer, and interpret the study. Cryptographic separation protects hidden truth, but not hypothesis-generation or analysis bias.
6. **Generalization risk.** Repeated outputs from one product configuration are observations of that configuration, not independent samples of “AI systems” in general.
7. **Product drift.** Silent model, policy, tool, or interface updates can change the treatment between trials unless configuration and time blocks are recorded.

## Decision
The existing direct transparent/opaque design is reclassified as:

> **RCL-PC: Runtime Capability Legibility Positive Control**

It may validate that the pipeline detects an obvious information effect. It must not be presented as evidence of consciousness, introspective access, or a general self-model faculty.
## Requirements before a headline confirmatory study
A main study must add all of the following:

- graded evidence rather than an exact truth label;
- preregistered signal reliabilities and base rates;
- trials where capability cues agree and conflict;
- forecasts after each evidence item, not only before and after a direct reveal;
- explicit attribution of which evidence changed the forecast;
- a normative posterior against which evidence integration can be scored;
- frozen product/configuration records for every block;
- an analysis program committed before the first included trial;
- a separation between positive-control results and headline estimates;
- replication across product configurations or model families before broad claims.

## Permitted claim boundary
A successful RCL-PC block may support:

> Under a frozen evaluated configuration, the system used explicit runtime-state information to improve probabilistic forecasts of a controlled action.

It may not support:

> The model understands itself, is conscious, possesses privileged introspection, or generalizes this calibration to native tools and deployment contexts.

## Stage gate
Stage 004 passes only when:

1. the positive-control analysis is executable and tested;
2. the positive-control protocol is frozen separately;
3. the nontrivial main-study blueprint has a falsifiable estimand;
4. no included behavioral data have been inspected before those artifacts are committed.

## Outstanding execution gate

No included RCL-PC trial may begin yet. The product-configuration schema exists, but the Stage 003 controller does not bind a completed configuration record to the signed trial ledger. Before `PC-RCL-001`, an extension must bind the block ID and configuration SHA-256 into `SAIS_CONTROLLER_READY`, every signed record, `SAIS_SEAL`, and `SAIS_REVEAL`; the collector and final analyzer must verify that same binding. A permanently excluded end-to-end validation trial must pass first.

This is an execution-integrity HOLD, not a reason to weaken or retrospectively edit the behavioral estimand.
