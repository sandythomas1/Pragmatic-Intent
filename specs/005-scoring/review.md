# Spec 005 review

2026-10-18, implementation preflight by the working agent (not an independent review).
Verdict: READY for scoped tooling implementation.

Resolved before code: oracle predictions are a separate complete stream so missed routes cannot
shrink the oracle denominator; Request slots are distinct from Inform values; unmapped requests
stay in detection; explicit invalid records fail outcomes while malformed envelopes abort; v1
remains the default and v2 is frozen before round-2 scoring. Free-text/LLM judging is explicitly
deferred rather than represented by exact act matching. No unresolved product choice blocks
the deterministic infrastructure requested by Sandy.

Implementation self-review: non-request null-category abstention, conflicting source act values,
foreign cue/slice IDs, source overwrite prevention, and native-Windows output newlines were
checked and fixed before closeout. Regression tests cover the corrected outcomes. V2 and v1
both score 29/30 on held-out round 2; no precision improvement is claimed without the fresh L3
judgments. The oracle stream is exported independently of predictions and is complete by condition.
Final verification and remaining human work are in [verification.md](verification.md).
