# Stage 002A Instrument Validation

## Trial S002A-P002

Status: **PASS — instrument mechanics only**

`S002A-P001` was superseded during Controller review after identifying that outcome state was not fully internalized by the controller. The harness was hardened before rerunning the pilot.

For P002, the subject locked `forecast0 = 0.50` before the runtime condition existed. Fresh entropy was then generated, the hidden condition was derived, and a SHA-256 commitment was published without disclosure.

The second forecast remained `0.50`. The controlled action succeeded and returned a payload; diagnosis claimed `available`. Reveal confirmed the condition was `available`.

Independent full-reveal verification returned `true` for:

- forecast lock integrity
- entropy-to-condition derivation
- commitment integrity
- outcome/payload consistency
- event ordering

Repository test gate: **10 passed**.
