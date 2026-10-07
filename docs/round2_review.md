# Round 2 calibration review

Reviewed 2026-10-06 against rubric v1. All 30 rows were completed. The Google
Sheets download had three unnamed columns; these were imported as `label`,
`fragment`, and `notes` after checking all IDs and utterances against the original
blinded sheet. The source download and previous blank labels file remain local.

The export is `data/annotations/levels_round2.csv`. Original answers are in
`label_initial`; `label_final` currently copies those answers and **has not been
adjudicated**. Case is normalized, including `Inf` → `INF`. Blank fragment flags
export as `0`. Notes and utterances remain in ignored local files.

## Proposed corrections to discuss

These suggestions apply the existing rubric. They are not a second independent
human annotation, agreement statistics, or permission to replace the initial
answers. Restricted dataset text is omitted; look up each ID in the local sheet.

| Item | Submitted | Proposed | Rubric reason |
|---|---|---|---|
| r2-01 | L1 | L0 | Plain question asks for the exact information wanted (R2). |
| r2-03 | L2 | L0 | Contains an explicit need statement. |
| r2-04 | L3 | L0 | Contains an explicit want statement; a scheduling constraint does not override it. |
| r2-06 | L1 | L0 | Imperative; politeness does not make a command L1. |
| r2-07 | L3 | L0 | Imperative asks for information. Speaker-role oddity can be noted separately. |
| r2-13 | L2 | L0 | Contains an explicit desire statement. |
| r2-14 | INF | L0 | Contains an explicit want statement. |
| r2-15 | L2 | L0 | Explicit need statement is the most direct request. |
| r2-17 | INF | L0 | Contains an explicit need statement alongside task information. |
| r2-22 | L2 | L0 | Contains an explicit need statement. |
| r2-23 | INF | NR | Satisfaction/closing, with no new actionable task detail. |
| r2-24 | NR | L0 | Plain question asks for information; judge wording independently of speaker role. |
| r2-25 | L2 | L0 | Explicit desire statement; unspecified price is ambiguity, not indirectness. |
| r2-26 | L1 | L0 | Need statement wins over the accompanying conventional request formula. |
| r2-29 | NR | L0 | Plain question asks for the exact information wanted. |

## Boundaries still requiring a decision

| Item | Submitted | Candidate | Decision needed |
|---|---|---|---|
| r2-10 | L2 | INF or L2 | Full-clause party/schedule statement: informing versus strong hint. R3 only settles fragments. |
| r2-19 | L1 | INF or L2 | Same boundary; no conventional L1 request formula is present. |
| r2-11 | INF | L0 provisionally | Decide whether searching/looking-for statements naming a desired service count as explicit goals. Existing rubric provisionally favors L0. |

The remaining 12 submitted labels have no proposed change in this review. Notes
about vague references and prices are useful, but should not change the request
form label (R1). All sentences have a main clause, so no additional fragment flags
are proposed.

## Continue coding this week

The evaluation harness can be developed now. It scores six-way directness levels
(`L0`–`L3`, `INF`, `NR`) and keeps informing distinct from social non-requests.
This avoids silently forcing `INF` into the older three-way Stage 1 design. The
final Stage 1 mapping is still to be documented before its experiments.

The first development run is a leave-one-dialogue-out majority baseline, using
only round 2's dev annotations. It holds out all variants of each dialogue and
produces identical predictions under the five context conditions by design.
Do not use its numbers to support the research hypotheses: labels are provisional,
there are only ten dialogues, and stronger indirectness levels are sparsely covered.

Next: adjudicate the rows above, document the settled boundaries, and implement
the TF-IDF baseline with a distinct training source and dialogue-separated dev
evaluation. Training-label availability and its supervision policy must be explicit;
DIRECT's variant names are not human L0–L3 labels. A separate frozen test sample
and the analysis plan remain necessary before reported experiments. No additional
calibration round is required to keep writing code this week.

## Development verification

On 2026-10-06, all 67 repository tests passed, including six new evaluation
tests; `git diff --check` passed. The real-data pilot scored all 30 items from ten
dialogues under five conditions. Its accuracy was 0% in each condition: the two
largest submitted classes, L2 and NR, tie at seven examples each, and leaving out
a dialogue changes the majority away from its held-out examples. This is a
limitation of this tiny sample and trivial baseline, not a context experiment or
a measure of annotation quality. Results are in ignored
`outputs/round2-pilot/metrics.json`; rerun after adjudication to regenerate them.
