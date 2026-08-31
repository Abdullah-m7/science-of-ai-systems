# Stage 002A Instrument Validation

## Trial S002A-P003

Status: **PASS — instrument mechanics only**

Earlier instrument trials were superseded during Controller review as the harness was hardened. P003 is the first pilot under frozen protocol version `SMI-CP/002A/1`.

The subject locked `forecast0 = 0.50` before the runtime condition existed. Fresh entropy was then generated, the hidden condition was derived, and a commitment binding protocol version, trial id, family, forecast lock, entropy, condition, and payload hash was published without disclosure.

The second forecast remained `0.50`. The controlled action succeeded and returned a payload; diagnosis claimed `available`. Reveal confirmed the condition was `available`.

Independent full-reveal verification returned `true` for protocol version, forecast lock, entropy-to-condition derivation, commitment integrity, outcome/payload consistency, and event ordering.

This pilot remains excluded from substantive claims about deployed AI systems because the same conversation participated in protocol development and subject interaction.
