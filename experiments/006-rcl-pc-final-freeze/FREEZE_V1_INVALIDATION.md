# Invalidation Notice — `sais-rcl-pc-v1`

Status: **INVALIDATED BEFORE INCLUDED TRIAL START**

The published tag `sais-rcl-pc-v1` points to commit `332075e3b887053c641f19b41f410e8f2c4721ee`.

During pre-execution PR review, the frozen product record was found to identify the subject model as `GPT-5.6 Pro`. The actual subject runtime for this research conversation is `GPT-5.6 Sol`.

Because product identity is part of the experimental system definition, this is a material provenance error rather than a cosmetic label issue. The tag is therefore retained unchanged for auditability but is **not authorized for behavioral data collection or scientific claims**.

No included `PC-RCL-*` issue or trial had started when the error was found. The GitHub issue search for titles containing `PC-RCL-` returned no included trial surfaces.

The corrected freeze is designated `sais-rcl-pc-v2`, with a new block identifier, configuration source commit, byte hashes, configuration binding, and manifest. Data from v1 must never be pooled with v2.