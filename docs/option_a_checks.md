# Option A: the remaining human checks

_Added 2026-10-13 with [spec 001 v1.2](../specs/001-pragmatic-intent-study/spec.md). Under option A,
directness levels come from the frozen `auto-v1` wording rules and intents come from MultiWOZ acts.
No new labeling rounds are planned. These three small checks are the only human input left. All
the sheets hold DIRECT text, so they stay in git-ignored folders. Open them in Excel and save with
**File → Save As → CSV UTF-8**._

**2026-10-18 continuation:** frozen `auto-v2` is implemented, with the same 29/30 (96.7%,
κ = 0.929) agreement as v1 on adjudicated round 2. That round contains no gold L3 examples.
A fresh precision check is ready at
`data/interim/auto_levels/auto-v2/spotcheck_L3/sheet.csv` (40 dev utterances, seed 20261018,
historical turns and the original v1 sample's turns excluded). This is the small rule audit,
not the dropped form/context/reveal annotation pipeline. Fill `verdict` and, for wrong rows,
`better_level`; keep `better_level` blank for an OK row. Save CSV UTF-8, then run:

```bash
python -m src.data.auto_levels_v2 spotcheck-report
```

The rules remain provisional until that fresh check is completed. V1 remains the default;
no L3 improvement is claimed from round 2 or the old development sheet. The freeze hash and
verification evidence are in [spec 005](../specs/005-scoring/verification.md).
Stage 2 and transfer input/scoring tools are now built; usage is in
[stage2_scoring.md](stage2_scoring.md). Model runs and the later human adequacy ratings remain pending.

| # | Check | Sheet | Rows | Time | When |
|---|---|---|---|---|---|
| 1 | Adjudicate round 2 | `data/interim/labeling/round2/adjudication_A1.csv` | 30 | ~15 min | **done 2026-10-17** |
| 2 | Spot-check rule L3 | `data/interim/auto_levels/spotcheck_L3/sheet.csv` | 40 | ~15 min | **done 2026-10-17** |
| 3 | Rate Stage 2 outputs | not built yet; needs model outputs | ~50 | ~25 min | November |

## 1. Adjudicate round 2

**Done 2026-10-17.** Q1 = **(a) `L0`**, recorded as rubric rule R8. `label_final` is written to
`data/annotations/levels_round2.csv` (`rubric_version` v2); `label_initial` is unchanged. 30 rows:
13 first labels kept, 16 changed to the suggestion, and r2-23 kept at `INF` against the `NR`
suggestion. Round 1 and 3 gold was not edited to match Q1 (see the rubric changelog).

**Why:** round 2 has never been checked against the rubric, and the rules were never tuned on it.
Its final labels become the fresh test for any improved rule version (`auto-v2`).

For each row, read `utterance`, `your_first_label`, `suggested` and `why`, then type your decision
in `label_final` (`L0` `L1` `L2` `L3` `INF` `NR` `?`). Follow [rubric v2](annotation_guidelines.md).
The suggestion is a starting point, not the answer: overrule it whenever the rubric says otherwise.
The sheet doesn't show what the rules predict, on purpose.

**Q1: decide this before the three rows marked `DECIDE`.** Rubric v2 contradicts itself on
"I need to leave / I want to leave …":

- The decision procedure (step 3) says any "I need / I want" statement is `L0`.
- R6's own example, "My destination is Broxbourne and I need to leave Tuesday afternoon.", is `L2`.

Choose one reading and use it for all three rows:

- **(a) `L0`.** "I need to leave after 5" is a need statement. This is simple, and the rules already do it.
- **(b) `L2`.** A need about *your own* schedule only hints at the request (find me a train).
  Then rubric v3 adds a rule: "I need/want to + travel verb (leave, arrive, depart, travel, go)"
  is `L2`.

Write your choice in the `notes` of the first `DECIDE` row. Send the sheet back and Claude will
write `label_final` into `data/annotations/levels_round2.csv`. `label_initial` never changes.

## 2. Spot-check the rule's L3 turns

**Done 2026-10-17. `auto-v1` L3 precision is 12/40 (30%).** When the rule was wrong, the right level was
`NR` 12 times (closings such as "that's all I needed" that the social-act check misses), `L2` 11 times
(a named detail outside the slot vocabulary), and otherwise `INF` 2, `L1` 2, `L0` 1. The rule's `L3`
must not be reported as a level on its own until `auto-v2` fixes it. This sheet has now been read,
so it can guide `auto-v2` but cannot test it: `auto-v2` needs a fresh L3 draw (a new seed, these
turns excluded) along with adjudicated round 2.

**Why:** only one of the 69 hand labels is `L3`, so the rules' `L3` has the least evidence behind
it. These are 40 dev turns drawn at random from those the rules call `L3` (seed 20261013, turns
from earlier rounds excluded). Dev only: nothing read here can enter the test split.

For each row:

- `verdict`: `ok` if `L3` is right under rubric v2, otherwise `wrong`;
- `better_level`: required when `wrong`. Give the level it should be (`L0` `L1` `L2` `INF` `NR` `?`);
- `notes`: optional.

Reminder: `L3` means no request formula and nothing wanted is named. A sentence that mentions a
day, time, place, cuisine, party size or the thing wanted is `L2`. An answer or a "no preference"
is `INF`. Then run:

```bash
python -m src.data.auto_levels spotcheck-report --level L3
```

It reports the share of `ok` rows (precision), with counts only, in `outputs/auto_levels/spotcheck_L3.json`.

## 3. Stage 2 output ratings (later)

Once a model has produced Stage 2 interpretations on dev, Claude builds a sheet of about 50
outputs. Each output is shown next to DIRECT's direct rewrite and the MultiWOZ intent. You mark
`pass` or `fail`, and those marks measure how well the LLM judge agrees with you.
