# Annotation Guidelines: Request Directness Level

_Rubric **v1**, 2026-09-26. Read this whole page before labeling. It is written so that a second
annotator who has never seen the project can apply it._

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

## Open questions (watch for these in round 2)

- **"I'm looking for X"** is very common in this data. It is provisionally `L0`, as a want statement:
  it states the user's goal and names the thing. The alternative is `L2`, on the reading that it only
  describes the user's situation. Decide once several examples have been seen.

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

- **v1 (2026-09-26):** added rules R1–R4 after calibration round 1 (15 items, 8/15 initial agreement
  with the reference labels), and added the "I'm looking for" open question.
- **v0 (2026-09-25):** initial labels L0–L3 (CCSARP), plus `INF`, `NR`, and `?`.
