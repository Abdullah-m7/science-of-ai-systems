# MOSAIC Literature Positioning

Snapshot date: `2026-09-01`

Status: focused positioning review; not a systematic review and not a priority claim.

## Closest lines of work

### Self-evaluation and knowledge calibration
Kadavath et al., *Language Models (Mostly) Know What They Know* (2022), study P(True) and P(IK): whether models can estimate correctness and whether they know an answer. They also show that relevant source material and hints can appropriately change predicted know-probabilities.

Preprint: `arXiv:2207.05221`

### Confidence updating and contradictory advice
Kumaran et al., *Competing Biases underlie Overconfidence and Underconfidence in LLMs* (Nature Machine Intelligence, 2026), identify both choice-supportive persistence and systematic overweighting of opposing advice relative to optimal Bayesian updating.

DOI: `10.1038/s42256-026-01217-9`

### Bayesian consistency of probabilistic beliefs
Chen et al., *LLMs Are Not (Consistently) Bayesian* (2026), treat models as information-processing rules and quantify an information-processing gap between observed probability updates and Bayesian updates. They report that some elicitation approaches are nearly Bayesian while others behave like learned heuristics.

Preprint: `arXiv:2605.06915`

### Broad awareness measurement
Li et al., *AwarenessBench* (ACL 2026), evaluate metacognition, self-awareness, social awareness, and situational awareness across 14,381 samples and report that stronger language modeling does not automatically imply stronger measured awareness.

DOI: `10.18653/v1/2026.acl-long.124`

### Conflicting evidence and abstention
Zhang and Wu, *Do LLMs Know When Evidence is Insufficient?* (2026), evaluate a five-level evidence-sufficiency gradient in RAG settings. Their conflicting-evidence condition produces high over-answer rates across evaluated models.

DOI: `10.32604/cmc.2026.086343`

## MOSAIC's narrower target
MOSAIC does not ask whether a model knows a fact, recognizes an evaluation context, or abstains from a RAG answer. It asks whether a **deployed AI system updates a probability about its own immediately testable runtime capability** according to controlled evidence reliability.

The hidden state is externally generated. The action outcome is executable ground truth. Numerical source reliability is disclosed. Source labels and order are manipulated independently of evidence content.

Each quartet holds truth, cue claims, and numerical reliabilities fixed while crossing label assignment and presentation order. Under the stated conditional-independence model, the final Bayesian posterior is identical across all four transformations. Final-forecast differences therefore isolate label and order distortion.

## Design differentiators
The intended contribution is the combination of:

- runtime self-capability rather than factual-answer confidence;
- post-baseline external state generation;
- two cues with explicit generative reliabilities;
- exact counterfactual label swaps and order swaps;
- named-source and neutral-source frames;
- Bayesian posterior oracle and information-processing-gap diagnostics;
- controlled action as outcome ground truth;
- quartet-level commit/seal/reveal provenance;
- eventual native-tool replication after synthetic-system validity.

The closest 2026 belief-updating work makes it especially important not to claim that any deviation from Bayes is uniquely a self-model failure. MOSAIC therefore reports general evidence-integration distortions and then asks whether those distortions persist when the uncertain proposition is the system's own capability.

## Novelty caution
No absolute first-in-world claim is frozen. Before publication, this positioning must be expanded through database search, citation chaining, concurrent-preprint review, and independent challenge from calibration, HCI, agent-evaluation, and judgment-and-decision-making perspectives.

Terms such as self-model or metacognition remain operational: they refer to observable forecasting and updating behavior, not consciousness or private subjective state.