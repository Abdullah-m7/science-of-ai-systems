# Research Charter

## Mission

Build an independent, reproducible science for studying advanced AI systems as deployed socio-technical systems rather than as model checkpoints alone.

## Core questions

1. What is the correct unit of analysis for a deployed AI system?
2. Which observed capabilities belong to the model, and which emerge from memory, tools, permissions, interfaces, or humans?
3. Can a system accurately model its own effective state and update that model after environmental change?
4. Can claims and actions be reconstructed from auditable evidence without access to hidden chain-of-thought?
5. Which findings survive changes in model family, language, product surface, time, and evaluation harness?
6. How should longitudinal AI systems be compared when their components change asynchronously?

## Scientific commitments

- Observable evidence over anthropomorphic interpretation.
- Pre-registered predictions where feasible.
- External or executable ground truth whenever available.
- Separate subject, experimenter, and judge roles where practical.
- Record system configuration, tool state, permissions, date, and harness with every run.
- Never treat self-report as proof of internal mechanism.
- Publish negative and null results alongside positive findings.
## Independence rules

The laboratory may study OpenAI, Anthropic, Google, open-weight systems, or future providers. Provider-specific findings must not be generalized beyond the tested configuration without evidence.

A system being useful in conducting a study does not make it a valid judge of its own performance. Self-evaluation is data; it is not ground truth.

## Evidence hierarchy

Preferred evidence, strongest first:

1. Executable or externally verifiable outcome.
2. Independent human or blinded evaluator with a frozen rubric.
3. Cross-model adjudication with disagreement reporting.
4. Subject-system self-report.

## Reproducibility minimum

Every reported result must identify, when observable: model/product label, date, conversation state, memory state, tool manifest, permission state, task version, attempt budget, evaluator, scoring code version, and raw outcome.

## Scope boundary

The program studies externally observable behavior and system interactions. It makes no claim to recover hidden chain-of-thought, private weights, or inaccessible internal states from verbal self-description.