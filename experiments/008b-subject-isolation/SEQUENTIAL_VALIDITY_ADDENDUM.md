# Stage 008B — Memory-Enabled Sequential Validity Addendum

Protocol: `SMI-CP/RCL-PC/SEQUENTIAL/1`

Status: **FROZEN BEFORE FIRST INCLUDED DISPATCH**

This addendum does not change the Stage 006 v2 primary estimand, thresholds, sample size, controller, configuration, or `PASS` / `FAIL` / `INCOMPLETE` / `INVALID` rules.

## Why this addendum exists

The v2 deployed-system configuration deliberately records `memory_state = enabled` and `customization_state = present`. A fresh conversation therefore resets active conversation context but must not be interpreted as proof that the deployed product has no cross-conversation state.

OpenAI documents that memory-enabled ChatGPT can reference information from previous conversations. OpenAI also documents that non-personalized Temporary Chats avoid memory but do not expose plugins, while personalized Temporary Chats may use existing memories and plugins. Changing to either Temporary Chat mode would therefore alter the frozen v2 system configuration rather than merely improve hygiene.

Official references, checked 2026-09-01:
- https://openai.com/index/memory-and-new-controls-for-chatgpt/
- https://help.openai.com/en/articles/8914046-temporary-chat-faq

## Scientific interpretation

RCL-PC v2 is a repeated randomized measurement of a **memory-enabled deployed AI system**. The 32 trials are not claimed to be independent and identically distributed model draws.

The controller creates a new hidden 256-bit trial key only after Forecast0 is publicly bound. Capability and legibility assignments for the current trial therefore are not disclosed by prior trial outcomes. Prior exposure may still change the subject's future forecasting policy, confidence, or evaluation awareness; that adaptation is part of the observed deployed-system trajectory and must be measured rather than silently assumed away.
## Administration rules

1. Preserve the frozen trial order `PC-RCL-001` through `PC-RCL-032`; do not reorder based on observed outcomes.
2. Use one new regular ChatGPT conversation per identifier under the exact frozen subject instructions.
3. Do not paste prior forecasts, outcomes, assignments, running statistics, or threshold progress into a later subject conversation.
4. Do not deliberately query ChatGPT memory for prior RCL-PC information during a trial.
5. Do not use Temporary Chat inside this v2 block; it is a different product state with different memory/plugin behavior.
6. Do not save a running behavioral summary in subject-facing material.
7. Integrity checks may run trial-by-trial, but behavioral aggregation remains forbidden until all 32 identifiers reach terminal states.
8. If the visible model label, client build, memory setting, customization state, or tool availability changes, stop the block under the existing Stage 006 rule.

## Secondary sequential diagnostics

After the frozen primary analysis is complete, a separate secondary report may compute:

- Forecast0 slope over trial index;
- absolute update slope over trial index;
- gain slope over trial index;
- lag-1 correlation for Forecast0, update magnitude, and gain;
- early-half versus late-half summaries;
- primary-effect estimates after prefixes 8, 16, 24, and 32, reported retrospectively only after trial 32;
- realized transparent/opaque and available/degraded counts by half.

These diagnostics describe adaptation or drift. They do not change the frozen qualification result and must not be used for optional stopping.

## Claim boundary

A v2 result applies to the recorded memory-enabled ChatGPT system trajectory. It must not be described as an estimate from memory-isolated sessions. A later replication may deliberately freeze memory off or another isolation regime as a separate block; those data must not be pooled with v2 without a new prespecified analysis.