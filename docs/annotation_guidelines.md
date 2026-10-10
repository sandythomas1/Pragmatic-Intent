# Annotation Guidelines: Request Directness Level

_Rubric **v2**, 2026-09-30. Read this whole page before labeling. It is written so that a second
annotator who has never seen the project can apply it._

## Revised-study scope (2026-10-09)

Rubric v2 and existing calibration labels remain unchanged. The [collection protocol](source_collection_plan.md) requires a separate, versioned contextual-function and interpretation supplement for original dialogue and literary exchanges. This wording-only rubric does not establish contextual request status: an INF utterance may act as a request in context. The current exporter does not implement the new schema, and no existing labels have been automatically remapped.

## The task

You will see one user utterance from a conversation with a booking/information assistant (restaurants,
hotels, trains, taxis, attractions). Give it **one label** saying *how directly the user makes their
request*, if they make one at all.

**Judge the wording alone.** Don't reconstruct or imagine the conversation around it. How much the
conversation helps is measured separately, by showing models different amounts of context. If the
level depended on context, the study's main hypothesis (context helps more as requests get less
direct) would be true by definition.

**The level is about how the user asks, not how clear the meaning is.** "Can you make it for five?"
asks directly, even though "it" is vague. Vague wording is *ambiguity*, which is a separate thing: note
it in the notes column, and don't let it change the level.

## Labels

| Label | Meaning | Invented example |
|---|---|---|
| `L0` | **Direct.** A command, a need/want statement, or a plain question asking for exactly the information wanted. | "Book a table for two." · "I need a train after 6pm." · "What's the hotel's phone number?" |
| `L1` | **Conventionally indirect.** A stock request formula about ability, willingness, or possibility. | "Could you book a table for two?" · "Can I get the phone number?" · "Would you mind checking trains after 6?" |
| `L2` | **Strong hint.** No request formula, but it names part of what's wanted (the item, time, party size, or piece of information). | "There are two of us, and we're free around seven." · "I still don't have the hotel's number." |
| `L3` | **Mild hint.** No request formula, and it doesn't name what's wanted. | "It's our anniversary tonight and I haven't planned a thing." |
| `INF` | **Informing.** Asks for nothing new, but gives the assistant usable task information: an answer, a constraint, or a preference, including "no preference". | "No preference on the area." · "Just the two of us." |
| `NR` | **No request.** Nothing task-related: thanks, goodbye, greetings, or turning down an offer. | "That's everything, thanks!" · "No need to book, I was just asking." |
| `?` | **Undecidable from the wording.** Use sparingly, and say why in the notes. | |

## Decision procedure

1. **Does the utterance ask for, or hint at, something the assistant should do or provide?**
   - No, and it carries no task information → `NR`.
   - No, but it carries task information → `INF`. If it's a fragment with no main clause
     ("5 people on Wednesday at 7."), also set `fragment = 1`.
   - Yes → go to step 2.
2. **Find the most direct request in the utterance and label that one.** "Pick one. I need the times."
   contains a command and a need statement, so it is `L0`, even if other sentences in the utterance are
   hints.
3. **Match its form, top to bottom, and take the first row that fits:**
   - A command, "I need / I want / I'd like …", or a plain question for the wanted information → `L0`.
   - "Can / could / would you …?", "Can I get …?", "Would you mind …?", "Is it possible to …?",
     "How about …?" → `L1`.
   - Mentions what's wanted, without a request formula → `L2`.
   - Doesn't mention what's wanted → `L3`.

## Rules settled in calibration

| # | Rule | Why | Settled |
|---|---|---|---|
| R1 | The level describes **how the user asks**, not how much context you'd need to understand them. | Otherwise "context helps most at L3" is true by definition (research plan, decision #2). | Round 1 |
| R2 | A **plain question** is `L0` when it asks for exactly the information wanted. A question about something else, asked in order to get something ("Is 7pm open?" in order to book), counts as a hint. | Gives requests for information a full L0–L3 scale, as action requests have. | Round 1 |
| R3 | **Fragments** that only list details are `INF` with `fragment = 1`. | By wording alone they ask for nothing. Whether they act as requests in context is exactly what the context conditions measure. The flag allows fragments to be analyzed separately or excluded. | Round 1 |
| R4 | A "no preference" answer is `INF`, and turning down an offer is `NR`. | "No preference" still constrains the task ("any area"). Declining gives the assistant nothing to act on. | Round 1 |
| R5 | **"I'm looking for X"**, "I'm looking to …", and "I'd like to find X" are `L0` want statements, not `INF` or `L2`. | They work like "I want X", which CCSARP counts as direct. They ask the assistant to find something, so they aren't `INF`. They are very common opening turns in this data, and in round 3 four of them got three different labels, so they need a fixed rule. | Round 3 |
| R6 | A hint that names a **detail of what's wanted** (destination, day, time, cuisine, party size) is `L2`, even if the thing itself ("a train", "a restaurant") is never named. `L3` is only for hints that name nothing wanted at all. | Matches the `L2` definition, which already counts time and party size. It gives `L3` a clear boundary instead of a sliding one. Example: "My destination is Broxbourne and I need to leave Tuesday afternoon." is `L2`. | Round 3 |
| R7 | A **request formula** fixes the level however clear or vague the request is. "Can you find an attraction in the centre?" is `L1`, not `L0`, even though it's perfectly clear. "How about a gastropub then?" is `L1`, not `L3`, even though it needs context. Commands such as "Find me …" stay `L0`. | Applies R1 to the most common round-3 error, where clarity pushed labels toward `L0` and vagueness toward `L3`. | Round 3 |

## Open questions

None open. Add new ones here as calibration finds them.

## Running a round

```bash
python -m src.annotation.levels sample --round 4 --split dev --triples 10   # blinded, shuffled sheet
python -m src.annotation.levels label  --round 4 --annotator A1             # terminal: one key per item; resumable
python -m src.annotation.levels sheet  --round 4 --annotator A1             # or: an Excel-ready CSV to fill in
python -m src.annotation.levels export --round 4 --annotator A1 --rubric v2 # writes data/annotations/levels_round4.csv
```

**In Excel:** open `data/interim/labeling/round<N>/labels_<annotator>.csv`. Fill in `label` (`L0` `L1`
`L2` `L3` `INF` `NR` `?`, any case), `fragment` (`1`, or leave it blank), and `notes`. Don't edit
`item_id`. Rows are matched by ID, so sorting is harmless. Save with **File → Save As → CSV UTF-8**. Plain "CSV" can garble curly
quotes, and the export rejects the file if that happens.

- Calibration rounds draw from `dev`. The gold sample is drawn from `test` once the rubric is
  frozen. (Rounds 1 and 3 were drawn from `test` before this rule existed. Their 5 and 8 turns are
  excluded from every later draw, so they never enter the gold sample.)
- Each draw takes whole DIRECT rows (all three variants), skips turn 0 (no context to vary) and
  rows with no mismatch donor, and skips turns labeled in any earlier round.
- Don't open `key.csv` while labeling: it shows the variant.
- Notes stay in the git-ignored `labels_<annotator>.csv`, because they often quote the utterance.
  The export holds IDs and labels only.
- After discussion, change `label_final` in the exported CSV directly. Never change `label_initial`.

## Label file format

Labels live in `data/annotations/levels_<round>.csv`, one row per utterance. **No utterance text goes in
these files**, because DIRECT's text can't be redistributed. The text is in the gitignored
`data/interim/labeling/`.

| Column | Meaning |
|---|---|
| `item_id` | ID within the round, e.g. `r1-07`. |
| `dialogue_id`, `turn_index` | Where the turn sits in MultiWOZ 2.1 (0-based, counting all turns). |
| `variant` | The DIRECT column: `target` (original), `direct`, or `indirect`. It is hidden from annotators while they label. |
| `label_initial` | The annotator's independent label, before any discussion. Use this for agreement statistics. |
| `label_final` | The label after discussion and rubric updates. This is the gold label. |
| `fragment` | `1` if the utterance is a fragment with no main clause, otherwise `0`. |
| `annotator` | A pseudonymous ID. `A1` is the first author. |
| `rubric_version` | The version that `label_final` follows. |

## Changelog

- **v2 (2026-09-30):** added rules R5–R7 after calibration round 3 (24 items, 9/24 initial agreement
  with the reference labels). The "I'm looking for" question is settled as R5. Most disagreements came
  from request formulas being judged on clarity (R7) and from where the L2/L3 boundary sits (R6).
  Round 3 was labeled on 2026-09-30, before round 2 was exported on 2026-10-06. Both were first
  numbered round 2 on separate machines, and this one was renumbered to 3 (IDs `r3-xx`) when the two
  histories were merged. Round 2 was labeled under v1.
- **v1 (2026-09-26):** added rules R1–R4 after calibration round 1 (15 items, 8/15 initial agreement
  with the reference labels), and added the "I'm looking for" open question.
- **v0 (2026-09-25):** initial labels L0–L3 (CCSARP), plus `INF`, `NR`, and `?`.
