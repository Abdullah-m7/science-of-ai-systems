# Stage 004 Literature Positioning

Snapshot date: 2026-08-31

Status: focused positioning review, not a systematic review.

## Nearby research
### Knowledge-boundary awareness
Yin et al. (Findings of ACL 2023) study whether language models distinguish answerable from unanswerable questions and report a substantial gap from human recognition of knowledge limits.

DOI: `10.18653/v1/2023.findings-acl.551`

### Self-aware tool use
Shen, Zhu, and Chen (EMNLP Industry 2024) introduce SMARTCAL and report tool misuse and overconfidence in tool choice across models and tool-use frameworks.

DOI: `10.18653/v1/2024.emnlp-industry.59`

### Broad awareness benchmarks
Li et al. (ACL 2026) introduce AwarenessBench across metacognition, self-awareness, social awareness, and situational awareness, finding that stronger language modeling does not automatically imply stronger measured awareness.

DOI: `10.18653/v1/2026.acl-long.124`

### Evaluation awareness
Li et al. (2026) decompose evaluation awareness into environment and model components and introduce EvalAwareBench with controlled evaluation cues.

Preprint: `arXiv:2605.23055`
## Distinction sought by this project
The current project does not primarily ask whether a model knows an answer, chooses a tool, or recognizes an evaluation cue.

Its target contribution is a method for manipulating and auditing evidence about the **effective runtime capability of a deployed AI system** after a baseline forecast has been locked.

The combination sought is:

- system-level rather than isolated-model measurement;
- post-forecast causal perturbation;
- hidden state generated outside the subject runtime;
- public commit–seal–reveal verification;
- probabilistic forecasts before action;
- graded and conflicting evidence sources;
- source-attribution reports compared with observable updates;
- eventual replication on native tools, permissions, memory, and retrieval.

## Novelty caution
No claim of first-in-world novelty is frozen here. A defensible novelty claim requires:

1. database searches beyond the focused sources above;
2. backward and forward citation chaining;
3. review of agent-evaluation, calibration, human–computer interaction, and distributed-systems observability literature;
4. explicit comparison against concurrent 2026 preprints;
5. independent reviewer challenge before submission.

Until then, repository language should use “we target,” “we propose,” or “to our current knowledge,” not an absolute priority claim.

## Concept boundary
Terms such as self-model, metacognition, and awareness refer only to observable forecasting and updating behavior unless a stronger operational definition is supplied. No inference about consciousness or private subjective states follows from these experiments.
