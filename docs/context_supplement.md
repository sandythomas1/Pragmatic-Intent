# Contextual Annotation Supplement (`ctx-v0`)

**Historical, inactive under option A (spec 001 v1.2).** No form/context/reveal sheets or taxonomy
approval are required for the active study. Use [Stage 2 act/transfer scoring](stage2_scoring.md)
instead. This draft remains available for possible later annotation work.

_Draft 2026-10-11, **awaiting Sandy's approval** (spec 003 T7). Rubric `ctx-v0`, intent taxonomy
`ctx-tax-v0` ([intent_taxonomy.csv](../data/annotations/intent_taxonomy.csv)), segmenter `seg-v1`.
Every example on this page is invented. Read the whole page before your first context sheet._

[Rubric v2](annotation_guidelines.md) says **how** a turn is worded. This supplement records what
the turn **does** in its original context (does it ask for something?) and **what the speaker
wants**. It covers both strata: `dialogue` (MultiWOZ user turns) and `literary` (screened Aesop and
King James exchanges, see [spec 002](../specs/002-literary-sources/spec.md)).

## Three sealed passes

Each item is labeled three times, and each judgment is made with no more evidence than it should
have. The tool builds a pass's sheet for an item only after your previous pass for that item is
exported, so the order can't be broken by accident.

| Pass | You see | You record |
|---|---|---|
| `form` | the target utterance only | rubric v2 label, fragment flag, notes |
| `context` | numbered prior context + the target | function, intent, slots, paraphrase, evidence, confidence, depth, notes |
| `reveal` | the target, your own context reading, and everything **after** the target | future dependence, notes |

Rows are shuffled and carry opaque IDs (`f-001`, `c-001`, `r-001`). Don't try to work out which
dialogue or story a row comes from, and don't look items up in the source files.

```bash
python -m src.annotation.context sheet  --pass form    --batch pilot1 --annotator A1
python -m src.annotation.context export --pass form    --batch pilot1 --annotator A1 --rubric v2
python -m src.annotation.context sheet  --pass context --batch pilot1 --annotator A1
python -m src.annotation.context export --pass context --batch pilot1 --annotator A1
python -m src.annotation.context sheet  --pass reveal  --batch pilot1 --annotator A1
python -m src.annotation.context export --pass reveal  --batch pilot1 --annotator A1
```

Sheets open in Excel. Edit only the label columns, keep every row, and save as **CSV UTF-8**.
Export checks every row and lists every problem with its row and item. Fix them and export again.

## Pass 1: `form` (wording only)

Apply [rubric v2](annotation_guidelines.md) exactly as written: `L0`, `L1`, `L2`, `L3`, `INF`,
`NR` or `?`. Set `fragment` to `1` when the utterance is a fragment, else leave it blank or `0`.
Judge the wording alone. Don't imagine the conversation or story around it.

## Pass 2: `context` (prior context only)

The sheet shows:

- `speakers`: who is talking to whom (`user → assistant`, or e.g. `Heron → Mole`);
- `context`: everything **before** the target, one numbered segment per line. In dialogues a
  segment is a turn (`[0] USER: …`, `[1] SYSTEM: …`). In stories it's a sentence of the
  narrative or verse, never the title or the moral;
- `target`: the utterance you are judging.

Nothing after the target is shown, and you must not use anything after it, even if you remember
it.

### `function`: what the turn does

Pick one value. **Precedence:** if the turn contains *any* request of the addressee, it's
`request`, even if it also informs, thanks or complains. Otherwise use the first value that fits,
in this order: `decline` > `inform` > `social` > `other`.

| Value | Use when | Invented example |
|---|---|---|
| `request` | The speaker asks the addressee to do, give, tell or allow something, **or proposes doing something together** ("let us…", "shall we…"). The wording can be anything: a command, a question, a hint. | "The night is long and my feathers are thin." said to someone who could build a fire · "Is there anywhere cheap near the river?" · "Let us dig before the rain." |
| `decline` | The speaker refuses or turns down an offer or suggestion, and asks for nothing new. | "No, that one's too far away." |
| `inform` | The speaker gives information and asks for nothing. | "We'll be arriving on Tuesday." after the assistant asked the day |
| `social` | Thanks, greeting, goodbye, apology, with no request. | "Thanks, that's everything." |
| `other` | Something else: an exclamation, a thought spoken aloud, a promise, a threat with no demand. | "What a fine view," said the Goat to itself. |
| `uncertain` | You **can't tell whether a request is present**, even with the context. Don't use it for an unclear intent: a request with an unclear intent is still `request`. | "It's getting cold in here." where nothing shows whether the hearer could or should act |

A turn that is `INF` in the form pass can still be a `request` here. That's exactly the case this
pass exists to capture, so don't let your form label decide the function.

### `intent` and `alt_intent`: what the speaker wants

Required for `request`, blank for `decline`, `inform`, `social` and `other`. For `uncertain` you
may name the candidate request you had in mind, or leave it blank.

Pick the intent from taxonomy `ctx-tax-v0`:

| Intent | Stratum | Required slots | Optional slots |
|---|---|---|---|
| `find_restaurant` | dialogue | none | area, price, food, name |
| `book_restaurant` | dialogue | people, day, time | name |
| `find_hotel` | dialogue | none | area, price, type, stars, parking, internet, name |
| `book_hotel` | dialogue | people, day, stay | name |
| `find_attraction` | dialogue | none | area, type, name |
| `find_train` | dialogue | none | departure, destination, day, leave_at, arrive_by |
| `book_train` | dialogue | people | train_id |
| `book_taxi` | dialogue | departure, destination | leave_at, arrive_by |
| `find_hospital` | dialogue | none | department |
| `find_police` | dialogue | none | none |
| `ask_attribute` | dialogue | attribute | entity |
| `give` | literary | none | object, recipient |
| `help` | literary | none | task |
| `permit` | literary | none | action |
| `stop` | literary | none | action |
| `inform_me` | literary | none | topic |
| `joint_action` | both | none | action |

- `ask_attribute` covers questions about a detail of a place or booking: phone number, address,
  postcode, entrance fee, reference number, travel time. Example: "What's their number?" gives
  `ask_attribute` with `attribute=number`.
- `joint_action` is for proposals that include the speaker: "Let us cross together" gives
  `joint_action` with `action=cross together`.
- `out_of_taxonomy`: a real request that no intent fits, e.g. "Can you change my booking to
  Friday?" or "Come down from the wall." Describe it in `notes`. It takes no slots. How often it
  fires tells us what the taxonomy is missing, so use it honestly rather than forcing a fit.
- `alt_intent`: optional, for a second reading you find genuinely plausible. Leave it blank
  otherwise. It must differ from `intent`.

If a turn makes two requests, label the one the turn is mainly about, and mention the other in
`notes`.

### `slots`: the details of the request

Write slots as `name=value;name=value`, using only the slot names listed for the intent.

- **Every required slot must appear.** If the source doesn't say it, write `name=?`. For
  example, "Book me a table, please." gives `book_restaurant` with `people=?;day=?;time=?`. Never
  invent a value.
- **Values are in the source's own words**, copied from the target or the prior context: `area=by
  the river`, not `area=centre`. Normalization is the scorer's job, not yours.
- Optional slots: fill them only when the speaker actually constrains them.
- A value may come from earlier context. "Yes, for four of us" after the assistant asked about a
  Tuesday table gives `book_restaurant` with `people=four;day=Tuesday;time=?`.

### `paraphrase`

Required for `request`. One sentence saying, directly, what the speaker wants, as if they had used
a plain command or question: "Light a fire so I can get warm." Keep it to the wanted outcome, not
the speaker's reasons. Single line, at most 500 characters.

### `evidence`

The numbers of the prior segments you relied on, e.g. `0;3`. Leave it blank when the target alone
was enough. Cite the segments that changed or decided your reading, not every segment you read.

### `confidence`

- `certain`: you would be surprised if a careful second annotator disagreed.
- `probable`: your reading is the best one, but another is defensible.
- `uncertain`: you're guessing between readings.

Confidence covers the whole row: function, intent and slots.

### `depth` (exploratory, optional)

How many interpretive steps lead from the words to the request. Count the links, not the length of
the story.

- `one_step`: one inference: "It's cold in here" → close the window.
- `multi_step`: a chain: "The Mole has a shovel" → the Mole can dig → the Heron wants a hole dug.
- `uncertain`: you can't say.

Leave it blank when you didn't judge it. Depth isn't L0–L3 and must not be read off the form label.

### `notes`

Anything worth telling an adjudicator. Notes are kept locally and are not part of the hashed
labels.

### Fields the tool derives (never typed)

- `request_status`: `present` for `request`, `uncertain` for `uncertain`, otherwise `absent`.
- `request_type` (computed at analysis time from your form and context rows):
  - `direct` for a request worded `L0`;
  - `indirect` for a request worded `L1`, `L2` or `L3`;
  - `form_unknown` for a request whose form label is `INF`, `NR` or `?`;
  - `uncertain` when request presence is uncertain;
  - `none` when there is no request.

An `INF` turn that functions as a request is `form_unknown`, never `none`.

## Pass 3: `reveal` (later evidence)

The sheet shows the target, your sealed context reading (`reading`, for reference only) and the
`continuation`: the rest of the dialogue, or the rest of the story including its moral. Record how
the continuation bears on your reading:

| `future_dependence` | Use when | Effect |
|---|---|---|
| `none` | The continuation says nothing about what was wanted. | none |
| `corroborates` | The continuation fits your reading: the addressee acts on it, or the speaker confirms it. | none |
| `conflicts` | The continuation shows a different reading was meant. | `needs_adjudication = true` |
| `required` | The request (or its intent) can only be recovered from what comes after. Without it you would not have got there. | `confirmatory_eligible = false` |

Don't revise your context labels because of what you read here. That's the point of the seal. If
you made a genuine **mistake** in an earlier pass (a typo, the wrong row, a rubric misread), use a
correction.

## Corrections

An exported label can't be changed by exporting again. Use `correct`, which keeps the old row
(marked `superseded`), appends the fixed one and logs both hashes in
`data/annotations/context_corrections.csv`:

```bash
python -m src.annotation.context correct --pass context --annotator A1 --item <item_id> --prepare
# edit data/interim/context/<batch>/correct_context_A1.csv, then:
python -m src.annotation.context correct --pass context --annotator A1 --item <item_id> --reason typo
```

| `--reason` | Use when |
|---|---|
| `typo` | You meant one value and typed another. |
| `wrong_sheet` | The labels belonged to a different row or sheet. |
| `wrong_annotator` | The labels were exported under the wrong annotator ID. |
| `rubric_misread` | You applied a rule wrongly and now read it correctly. |
| `other` | Anything else. Say what in the correction's `notes`. |

The tool records `later_passes_sealed = true` if you had already seen a later pass's sheet for
that item. That correction may be influenced by later evidence, and analyses can set it aside.
Corrections are for mistakes, not second thoughts after the reveal.

## Backing up free text

Slot values, paraphrases and notes are **not committed** (they often quote the source). They live
only in `data/interim/context/` (`<pass>_<annotator>_text.jsonl`). Committed rows hold a
`text_sha256` so a lost or altered file is detected.

**After every export or correction, copy the whole `data/interim/context/` folder to the
project's Google Drive folder**, replacing the previous copy.

Run `python -m src.annotation.context validate` before each backup and after any restore. A
`[local-text]` or `[row-hash]` finding means the local text no longer matches the committed
labels: restore the folder from the last good backup rather than editing either file.

## Disclosure: `prior_exposure`

Sandy screened the literary candidates (spec 002), so Sandy has already read each literary target
in its story, ending included, before labeling it. Sandy's literary labels in **all three passes**
are therefore flagged `prior_exposure` in coverage reports and disclosed as a limitation. Sandy's
dialogue labels are not affected. Blind literary labels from a second annotator can be added
later under their own annotator ID.

## Changelog

- `ctx-v0` (2026-10-11): first draft with taxonomy `ctx-tax-v0` and segmenter `seg-v1`.
