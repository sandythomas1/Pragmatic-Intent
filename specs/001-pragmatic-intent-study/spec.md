# Overall Specification: Pragmatic Intent Research Study

**ID:** 001-pragmatic-intent-study

**Version:** 1.0 draft, 2026-10-09

**Owner:** Sandy Thomas

**Faculty discussion:** Dr. Benjamin Sanders, meeting 2026-10-08

**First milestone:** class research paper and model results, December 2026; exact due date pending

**Second milestone:** publication development toward WDSI; official year/deadline/format pending

**Status:** specification for review; not an approved study protocol, preregistration or completed experiment

## 1. Purpose and source of truth

This specification consolidates the complete study into one reviewable contract: what will be
collected, annotated, built, evaluated, analyzed and delivered, with dependencies and completion
criteria. It does not implement the research pipeline.

The [interactive guide](spec-guide.html) is a standalone explanatory view of this version.
Its controls simulate presentation and workload; they do not approve the protocol, change
repository configs, launch experiments, collect research judgments or establish study progress.

The original [proposal PDF](<../../docs/Pragmatic_Intent_Detection_Proposal_Plain .pdf>) remains
the historical proposal. The [revised research plan](../../docs/research_plan.md),
[collection protocol](../../docs/source_collection_plan.md),
[draft analysis plan](../../docs/analysis_plan.md),
[rubric v2](../../docs/annotation_guidelines.md) and
[revision report](../../docs/research_revision_2026-10-09.md) supply detailed methods and history.
This master spec consolidates their revised design; a later methodological change must update
this spec and the applicable detailed document, with rationale and version/date. The analysis
plan requires a separate freeze record before reported test runs.

## 2. Problem and retained research question

A user can state a fact while intending a request. Literal wording alone may not identify whether
there is a request or what action/information is intended. Existing weak rewrite labels and
form-only annotations do not independently establish contextual speaker intent.

Retain the exact original question:

> How do conversational context and linguistic ambiguity interact when machine learning and language models infer a user's underlying intent?

The central empirical interest is whether additional relevant context benefits less explicit
requests more. The study distinguishes detecting a request from interpreting its content.
It investigates model behavior on source-grounded examples, not subsequent human behavior or
autonomous execution of inferred actions.

## 3. Goals, non-goals and completion principles

### Goals

- Preserve the question and detection/interpretation comparison.
- Adopt the professor's human-authored source-gathering methods, including screened literature.
- Measure context benefits, indirectness effects, ambiguity and unsupported inference.
- Deliver reproducible class results and a paper by the actual December deadline.
- Produce a defensible foundation for stronger validation and later publication.

### Non-goals for December

- Invent a new neural architecture or solve general pragmatics.
- Infer morals, theological truth, joke explanations or all character motives as assistant requests.
- Generate main-benchmark utterances, contexts, synthetic contrastive twins or complete request ladders.
- Guarantee H2 significance, a target accuracy, publication acceptance or pretraining absence.
- Deploy an assistant, call real tools on inferred requests, recruit participants without the
  relevant determination, or start paid model runs from this specification.
- Expand to every genre, language, intent category and model family before the class deliverable.

A negative or null hypothesis result is acceptable. Completion requires trustworthy evidence
and explicit limits, not positive support for the expected hypothesis.

## 4. Terminology and task contract

| Term | Definition in this study |
|---|---|
| Pragmatic inference | Recovering what a speaker communicates beyond the literal sentence, using source-grounded evidence. |
| Indirect speech act | A communicative act expressed through a surface form that is not a direct statement of that act. |
| Conversational implicature | A contextually supported implied meaning; not every implicature is a request. |
| Indirectness/form | L0 direct, L1 conventional indirectness, L2 strong hint, L3 mild hint under a wording-only rubric. |
| Contextual function | What the speaker is doing in original context: requesting, informing, declining, social exchange or another function. |
| Ambiguity | Supported alternative readings or uncertainty, measured separately; disagreement is a proxy, not proof. |
| Gold | Adjudicated historical interpretation supported by source evidence; provisional when independent validation is absent. |
| Episode/group | All related dialogue turns, variants, literary retellings/translations or near-duplicates kept together across splits. |
| Oracle Stage 2 | Interpretation scored on every eligible gold indirect request, independent of routing predictions. |
| Routed hybrid | Stage 1 identifies indirect requests and forwards them for interpretation; missed routes fail end-to-end scoring. |
| Mismatch | Deliberate corruption with an unrelated preceding window, not an authentic alternative conversation. |

### Stage 1: detection

Represent request presence separately from request type. Contextually validated requests with
L0 are direct; L1-L3 are indirect. Genuine non-requests have no-request type. An item with
known request presence but unknown form remains eligible for binary request detection and
is excluded from three-way/type and level-dependent endpoints. Preserve uncertainty instead
of forcing a label. Wording-only INF does not automatically imply contextual no-request.

### Stage 2: interpretation

Predict supported intent category, required key slots where applicable and a concise direct
paraphrase. A request outside the represented taxonomy remains a request and is excluded only
from the relevant in-scope interpretation endpoint. An ambiguous full-context case belongs to a
challenge analysis unless an admissible multi-reading policy is frozen beforehand.

All eligible end-to-end procedures must recover intent on direct routes as well as indirect routes.
A classifier that outputs only request type belongs in detection tables, not an end-to-end intent
comparison. Declare any shared interpretation component when attributing differences to model family.

## 5. Study design and retained hypotheses

Context is manipulated within item. Indirectness is observed in original wording, not randomized.
Cross-level relationships may reflect source, intent, wording length and speaker differences.
Source strata remain separate, with any pooled analysis explicitly exploratory and justified.

| ID | Hypothesis | Role |
|---|---|---|
| H1 | Performance falls as request indirectness increases. | Replication; no novelty claim. |
| H2 | Context helps more as indirectness increases. | Primary interaction of interest. |
| H3 | Context benefit differs by model family. | Secondary; one model/family supports limited descriptive comparison. |
| H4 | Detection degrades more slowly than interpretation. | Same gold indirect-request items/conditions; oracle and routing losses separated. |
| H5 | Intent categories differ systematically in difficulty. | Exploratory, subject to coverage. |

Primary H2 endpoint: historical-gold request detection AND intended-category recovery, plus
applicable required slots under the frozen taxonomy. Estimate full-minus-none correctness
benefit per L0-L3 and test the context-by-level interaction when the sample supports it.
Detection-only contrasts are secondary. A context main effect cannot establish H2.

Clarification is an exploratory slice because it presupposes prior discourse. Implication depth
is an independently annotated exploratory evidence-chain feature, not an alternative L0-L3 scale.

## 6. Scope and December success profiles

| Profile | Sample goal | Models and outputs | Claim boundary |
|---|---|---|---|
| December target | 160-240 dialogue test items across at least 50 groups; 20-40 literary items across at least 10 story families. | Majority/TF-IDF, one encoder, one LLM, small hybrid; complete context comparisons and paper. | Confirmatory H2 only if pilot coverage/power and frozen protocol justify it. |
| December fallback | 120 dialogue test items across at least 30 groups plus a documented literary pilot. | Preserve simple baselines, feasible model comparisons, Stage 2 and paired context results; drop added model families/genres first. | Exploratory/pilot claims where necessary; independent-rater absence remains explicit. |
| Publication extension | Pilot-informed expansion; no fixed size or deadline invented here. | More source groups/works, raters and model families; replication and permitted release. | Stronger validation and justified inferential power; confirmed venue requirements. |

These are collection goals, not current counts, power guarantees or acceptance thresholds.
The development pilot is additional: approximately 60 screened candidates, 40 original dialogue
and 20 literary. Pilot groups never enter test. Aim for 25-40 requests per L0-L3 level plus
authentic negatives. Exact quotas and represented intents are fixed after pilot review.
Do not manufacture rare levels, empty intent cells or genre balance.

Independent validation is a goal, not an assumption about staffing. Seek full test double labeling;
minimum course goal is a stratified 25% and difficult literary cases. A solo-rater deliverable is
a provisional pilot, with no independent agreement or human-baseline claim. Study quality is
not inferred from item count alone.

## 7. Source gathering, annotation and leakage controls

### Source strata

- **Primary assistant dialogue:** original MultiWOZ target turns and actual preceding history,
  using the current join. Preserve official train/dev/test dialogue assignments.
- **Auxiliary training/diagnostics:** DIRECT's human-written rewrites, with explicit weak label
  policy and fact-drift review. They are elicited paraphrases, not natural gold indirectness.
- **Literary transfer:** addressed speech from pinned human-authored editions, initially held
  out of fine-tuning and prompt examples. Screen Aesop and the meeting's John 2:1-11 candidate;
  no gold reading is assumed from the story's fame.
- **Reference/optional screened controls:** Circa and conversational-implicature resources,
  independently reviewed for contextual function.
- **Excluded from the main human-only benchmark:** LLM-generated IndirectRequests or newly
  written input ladders, twins and invented contexts.

Every source and item has an inclusion/exclusion record. Candidate selection must not depend
on model errors. Narration without addressed speech may support an exploratory pragmatics
discussion but is not automatically a request item. Retain exact text, locators and evidence.
OCR corrections are logged; modernization/paraphrase creates a different input and is outside core scope.

### Annotation passes

1. Wording-only form, blinded to variant/source conclusions and model predictions.
2. Original full-context function and request presence/type.
3. Supported intent/required slots/paraphrase, evidence and alternatives.
4. Independent none/one/full judgments where feasible, assigned to avoid full-story recall.
5. Exploratory evidence-chain depth under a separately piloted rubric.

Preserve initial labels, final adjudication and rubric version separately. Published explanations,
later replies and story outcomes are corroboration, not gold authority or model input.
Exclude future-evidence-only gold from confirmatory endpoints; keep its exclusion rationale.
Protect annotator identities with pseudonyms; text-bearing notes remain local when source restrictions apply.

### Splits and freezes

Exclude entire previously inspected test dialogues, including dialogues containing rounds 1/3
calibration turns. Keep all variants, repeated episodes, retellings and translations together.
Training, prompt examples and manual dev review cannot include untouched test groups.
Freeze IDs, source/text hashes, label version, splits, exclusions, renderer/donor mapping and
analysis choices before reported test scoring. Amendments after freeze are dated and disclosed.

## 8. Context input contract

| Condition | Information available | Role |
|---|---|---|
| none | Exact target and fixed source-grounded role identifiers where required. | Utterance-only ablation. |
| one | Identical target and last preceding source turn/unit. | Immediate-context ablation. |
| full | Identical target and predefined preceding source window. | Relevant-context comparison. |
| mismatched | Identical target plus unrelated same-stratum/split window matched on length and format. | Corruption robustness control, reported separately. |
| mismatched_one | Optional matched one-unit donor. | Additional control, not required for December core. |

Dialogue one means the preceding speaker turn; literary one means the preceding speech/narrative
unit under a frozen segmentation rule. Report strata separately. Choose a common input budget
for model comparisons, record truncation and cue visibility, and never silently drop a crucial cue.
Titles/verse labels revealing a canonical story should be omitted from model inputs when unnecessary.

No ending, future reply, moral, gold paraphrase, annotation note or explanation enters input.
Compatible mismatch donors stay in the same split/stratum; review accidental helpful cues.
If no donor exists, retain the item for genuine-context contrasts but disclose exclusion from
the paired control set. Every contrast has an explicit common-item denominator.

## 9. Data and prediction interfaces

These are versioned contracts to implement, not schemas already supported by the current exporter.

| Record | Required information and invariants |
|---|---|
| Source | ID, canonical URL, edition/translation, authorship type, artifact/hash, acquisition date, rights/release mode. |
| Episode/item | Stable ID, source/episode/split group, official split where applicable, locators, speaker/addressee, verbatim target/prior spans. |
| Annotation | Wording form, contextual function, request presence/type, in-scope intent(s), required slots, gold paraphrase, confidence and evidence. |
| Adjudication | Independent initial judgments, pseudonymous rater IDs, rubric version, alternatives, final decision and rationale. |
| Condition | Target hash, source spans/unit segmentation, token budget, truncated/cue flags, donor ID, rendering hash and condition version. |
| Prediction | Run/model/recipe ID, item ID, condition, seed where relevant, request output, intent/slots/paraphrase, parse/abstain/transport status. |
| Run | Git commit/dirty flag, data/config hashes, checkpoint/API version, seed, prompt revision, package versions, hardware, runtime/cost and provenance. |
| Score | Endpoint, eligible/common-set IDs, exclusions and reasons, denominator, point estimate, uncertainty and output artifact hash. |

Uncertain form/function is not silently coerced. Missing, duplicate or foreign IDs and invalid
schema/condition mappings are rejected before aggregate scoring. An invalid model response is
an error, not an excluded observation. Repeated transport failures follow a frozen retry rule;
their counts remain visible. Restricted source text and raw prompts/outputs stay local;
publishable metadata/aggregate results cannot expose prohibited text or annotator identity.

## 10. Functional requirements

| ID | Requirement | Delivery scope | Starting state |
|---|---|---|---|
| FR-01 | Preserve the research question | December | Defined |
| FR-02 | Register and screen human-authored sources | December | Extend existing |
| FR-03 | Collect a development-only pilot | December | Planned |
| FR-04 | Separate form, function and supported intent | December | Extend existing |
| FR-05 | Validate human gold and ambiguity | December | Decision pending |
| FR-06 | Protect source groups and freeze the dataset | December | Extend existing |
| FR-07 | Render paired context conditions | December | Extend existing |
| FR-08 | Compare a feasible December model panel | December | Extend existing |
| FR-09 | Score the new tasks and routing failures | December | Planned |
| FR-10 | Analyze the interaction with honest uncertainty | December | Draft |
| FR-11 | Position the study with a bounded review | December | Planned |
| FR-12 | Produce the December paper and results package | December | Planned |
| FR-13 | Extend the study for publication | Publication | Later |
| FR-14 | Release a source-compatible research package | Publication | Later |

### FR-01: Preserve the research question

**Scope:** December. **Starting state:** Defined.

Retain the original context-and-linguistic-ambiguity question, two-stage framing and H1-H5. Operationalize indirectness by wording and ambiguity by independent judgments.

**Acceptance:** The frozen protocol and paper quote the original question; form, contextual function and ambiguity occupy separate fields.

### FR-02: Register and screen human-authored sources

**Scope:** December. **Starting state:** Extend existing.

Use original assistant dialogue for primary gold; collect addressed literary exchanges as transfer. Record editions, locators, provenance, rights, hashes and exclusions. Main benchmark inputs are not generated or rewritten for balance.

**Acceptance:** Every accepted item reconstructs to a pinned source with speaker, addressee and prior evidence; inclusion is independent of model performance.

### FR-03: Collect a development-only pilot

**Scope:** December. **Starting state:** Planned.

Screen about 60 candidates: 40 original dialogue and 20 literary. Inspect level, function, intent, genre and group coverage before selecting quotas.

**Acceptance:** Pilot inventory and inclusion/exclusion log exist; no pilot group enters the untouched test sample.

### FR-04: Separate form, function and supported intent

**Scope:** December. **Starting state:** Extend existing.

Preserve rubric v2 and initial historical labels. Add contextual function, request presence/type, intent, required slots, paraphrase, evidence and uncertainty in a versioned supplement.

**Acceptance:** Wording-only INF may be contextual request; out-of-scope requests stay requests; unknown form is not forced into L0-L3.

### FR-05: Validate human gold and ambiguity

**Scope:** December. **Starting state:** Decision pending.

Seek independent labeling of all new test items; minimum course goal is a stratified 25% plus difficult literary items. Use initial labels for agreement and separate adjudication. Independent condition judgments support a human baseline.

**Acceptance:** Agreement has raters, denominator, sampling and rubric version. Without independent raters, gold is provisional and human-baseline/ambiguity agreement claims are absent.

### FR-06: Protect source groups and freeze the dataset

**Scope:** December. **Starting state:** Extend existing.

Keep official dialogue splits; exclude whole previously inspected test dialogues. Group variants, translations, retellings and near-duplicates. Hold literary test families out of training and prompts.

**Acceptance:** Split intersections are empty; IDs, hashes, exclusions, contexts and donor mappings are frozen before reported test scoring.

### FR-07: Render paired context conditions

**Scope:** December. **Starting state:** Extend existing.

Keep target identical under none, one and full preceding context. Treat same-stratum, same-split matched donors as corrupted mismatch controls. Exclude later replies, endings, morals, gold and commentary from input.

**Acceptance:** A common item set supports each contrast; target hashes agree; future-evidence leakage and missing donors are detected and reported.

### FR-08: Compare a feasible December model panel

**Scope:** December. **Starting state:** Extend existing.

Run majority/TF-IDF, one encoder, one instruction-tuned LLM and a small routed hybrid. Keep weak DIRECT supervision explicit. Direct routes must output an intent for end-to-end scoring.

**Acceptance:** Pinned recipes, checkpoints, seeds, training policy and dev-selected prompts produce all frozen test conditions. No test-based model selection.

### FR-09: Score the new tasks and routing failures

**Scope:** December. **Starting state:** Planned.

Implement contextual-gold adapters and structured Stage 2 scoring. Report request metrics, oracle interpretation, end-to-end success, required slots, invalid outputs and non-request false positives.

**Acceptance:** Missing/duplicate IDs and invalid schemas fail validation; routing misses count as failures; oracle Stage 2 covers every eligible gold indirect request.

### FR-10: Analyze the interaction with honest uncertainty

**Scope:** December. **Starting state:** Draft.

Freeze paired contrasts, grouped bootstrap, dependence model or descriptive fallback, exclusions and secondary comparison correction. Report literary results separately. Pilot simulation determines whether H2 is confirmatory.

**Acceptance:** A context main effect is not labeled an interaction; sparse/underpowered analyses remain exploratory; null findings can satisfy study completion.

### FR-11: Position the study with a bounded review

**Scope:** December. **Starting state:** Planned.

Map pragmatic inference and unsupported interpretation literature from 2015-2025 plus a separate 2026 competitor update. Log search dates/strings, screening and task-specific metrics.

**Acceptance:** Paper explains the gap with primary references; incomparable hallucination metrics are not pooled into a worldwide accuracy.

### FR-12: Produce the December paper and results package

**Scope:** December. **Starting state:** Planned.

Deliver a paper, model comparison tables, context-by-level figures, source/annotation datasheet, error audit, configs, predictions and reproduction instructions.

**Acceptance:** Every reported number links to a frozen run and denominator; the class due date determines final writing/reproduction buffer.

### FR-13: Extend the study for publication

**Scope:** Publication. **Starting state:** Later.

After the class, expand independent raters, groups, literary works and model families; replicate with justified power and verify the WDSI call and format.

**Acceptance:** Venue date/format are confirmed; stronger validation and a separate replication support publication-level claims.

### FR-14: Release a source-compatible research package

**Scope:** Publication. **Starting state:** Later.

Release only source-permitted text or stable references, own annotations and reconstruction instructions. Preserve notices and keep restricted text and secrets local.

**Acceptance:** Release manifest assigns permitted content per source; no restricted DIRECT text or private annotator identity enters GitHub.

## 11. Technical boundaries and work packages

This is a local batch research project using Python 3.12, existing modules/configs and uv.lock.
No frontend/backend service, database or cloud deployment is needed. The guide uses self-contained
HTML/CSS/JavaScript because an offline explainer does not require the preferred application stack.

| Component | Starting position | Needed extension |
|---|---|---|
| Source downloader/join | src/data/ and pinned data/sources.toml exist. | Literary source registration, locator extraction and screened item adapter. |
| Annotation | src/annotation/ and historical form-label CSVs exist. | Contextual supplement, separate evidence/function records and validation. |
| Context rendering | DIRECT loader supports context and donors. | Source-aware original/literary rendering, invariant checks and manifests. |
| Model runs | src/stage1/ supports weak TF-IDF/encoder training. | Contextual gold adapter, structured LLM outputs and declared hybrid routing. |
| Evaluation | src/evaluation/ supports form/weak-label dev scoring. | Stage 2, oracle/end-to-end, invalid-output handling and source/group reporting. |
| Analysis/report | Draft methods exist. | Frozen analysis implementation, figures/tables and reproducible class report. |

| Package | Work | Dependencies | Done evidence |
|---|---|---|---|
| WP-01 | Resolve course deadline/resources; adjudicate round 2. | Existing context/rubric. | Due date record; immutable initial and documented final labels. |
| WP-02 | Register sources and screen dev pilot. | WP-01 scope. | Candidate inventory/exclusion log; source hashes/locators. |
| WP-03 | Pilot contextual supplement and independent judgments. | WP-02. | Versioned rubric, agreement/limitations and taxonomy. |
| WP-04 | Collect untouched groups and validate splits. | WP-03 decisions. | Group leakage audit and source/label manifest. |
| WP-05 | Render contexts and verify donor/cue invariants. | WP-03 stable contract; WP-04 for final freeze. | Deterministic common-set manifest and target equality. |
| WP-06 | Build contextual adapters and Stage 2/routing scorers. | WP-03 stable contract; dev fixtures. | Contract/error/denominator tests; dev predictions. |
| WP-07 | Train/run models on dev; choose recipes/prompts. | WP-05/06 dev interfaces. | Baseline outputs and pinned candidate recipes. |
| WP-08 | Decide H2 feasibility and freeze dataset/analysis/models. | WP-04/05/06/07; pilot statistics. | Freeze record, hashes, final comparison list. |
| WP-09 | Run the held-out grid and hybrid. | WP-08. | Complete validated predictions and provenance. |
| WP-10 | Analyze, audit errors and produce figures. | WP-09, frozen analysis. | Traceable contrasts, intervals, exclusions and limitations. |
| WP-11 | Write/reproduce December paper and demo. | WP-10; literature review may start at WP-01. | Course delivery package and reproduction evidence. |
| WP-12 | Expand validation and replicate for publication. | WP-11 and confirmed venue requirements. | Stronger study, manuscript and permitted release. |

Model development and scorer work can proceed on dev while final annotation is collected.
No reported test run bypasses WP-08. The task breakdown is a dependency plan, not a claim that
these packages have been implemented or approved for immediate paid execution.

## 12. Non-functional requirements

- **NFR-01 Reproducibility:** same versioned source/config/seed yields deterministic data and
  rendering hashes; model nondeterminism and hardware differences are documented.
- **NFR-02 Auditability:** every reported value links to eligible IDs, denominator, data/model
  revision and run artifact. Seeds/context variants do not inflate independent sample size.
- **NFR-03 Data handling:** source rights, pseudonymous annotations and secrets controls apply
  to local prompts, logs, git and any later release. No credentials or restricted raw text in git.
- **NFR-04 Feasibility:** develop on CPU/RTX 5060 WSL2; reported GPU recipes use the lab RTX 4090
  when available. Respect memory, model access and a separately chosen spending cap.
- **NFR-05 Task isolation:** no real-world action is executed; dialogue/literary content is treated
  as data, not permission to call tools or obey embedded instructions.
- **NFR-06 Compatibility:** preserve existing annotations, weak supervision, dependency pins and
  original proposal. Additive adapters have explicit schema versions and migration history.
- **NFR-07 Guide portability:** the HTML opens offline from a local file, with no CDN, remote API
  or framework install; it embeds the master specification and snapshot/version metadata.
- **NFR-08 Guide accessibility:** native labeled controls, keyboard operation, focus visibility,
  semantic headings, readable contrast, reduced-motion respect, and no overflow at 360px.
- **NFR-09 Guide honesty:** all example text is clearly illustrative and excluded from corpus;
  no invented results, fabricated completion percentages or simulated choices treated as progress.

## 13. Evaluation and statistical requirements

| Metric | Population/denominator | Purpose |
|---|---|---|
| Request precision/recall/F1 and confusion matrix | Settled contextual request presence. | Missed requests and false positives. |
| Three-way macro-F1 | Settled request type; unknown form excluded with counts. | Direct/indirect/non-request distinction. |
| Oracle intent/required-slot accuracy | All eligible gold indirect requests, independent of route. | Interpretation ability without routing bias. |
| End-to-end correctness | Identical eligible request items by condition. | Primary complete-pipeline endpoint. |
| Non-request false-positive rate | Original-context genuine non-requests. | Over-inference. |
| Human uncertainty/initial agreement | Independent condition judgments; explicit sample/rater counts. | Ambiguity and context recoverability. |
| Unsupported additions / paraphrase quality | Fixed stratified human-audited output sample. | Faithfulness, supplementary to structured scoring. |

Historical gold stays fixed for genuine-context ablation; condition-specific plausible human
readings are separately reported. Mismatch scores refer to a corrupted-input robustness task,
not a newly established historical intention.

Compute paired context contrasts per level and source, using complete groups for bootstrap.
Average seeds within model/item/condition before group resampling; separately report seed variation.
The proposed mixed-effects endpoint uses context, categorical form level and model, controlling
intent and accounting for dialogue and item dependence. Package, contrasts, estimation,
convergence/separation fallback and multiplicity family remain D-07 choices to freeze on dev.
Use pilot simulation before declaring power. If unsupported, prerecord descriptive paired
contrasts and exploratory H2. Do not upgrade a post-hoc significant result to a preregistered claim.

The interpretation audit distinguishes literal reading, wrong intent/slot, missed cue, over-inference,
unsupported addition, source mismatch, malformed response and routing failure. Human gold uncertainty
is an item property, not a reason to drop a model error after seeing its prediction.

## 14. Schedule and deliverables

These dates are working windows from the existing revised plan, not verified submission dates.

| Window | Milestone | Work | Exit deliverable |
|---|---|---|---|
| Oct 12–18 | Frame + screen | Adjudicate round 2, screen the 60-candidate dev pilot, confirm deadline and resources. | Source inventory, exclusion log and provisional taxonomy. |
| Oct 19–25 | Calibrate + decide | Pilot contextual labels, inspect level/genre coverage, run weak-label baselines on dev. | Agreement/feasibility report or explicit solo-rater limits. |
| Oct 26–Nov 1 | Collect + freeze | Collect untouched groups; freeze gold, context, splits and proposed analysis. | Manifest, hashes, datasheet and analysis freeze record. |
| Nov 2–8 | Build + validate | Implement task adapters and Stage 2 scoring; train baseline/encoder; validate LLM on dev. | Verified scorers, reproducible dev outputs and pinned models. |
| Nov 9–15 | Run the core grid | Use frozen models/prompts on held-out context conditions; run hybrid. | Complete predictions, seeds, runtime/cost and provenance. |
| Nov 16–22 | Analyze + audit | Compute paired contrasts and intervals; inspect over-inference, source bias and errors. | Tables, figures, error taxonomy and claim limits. |
| Nov 23–29 | Write the paper | Explain sources, methods, model comparisons, findings and limitations. | Full draft with reproduction instructions. |
| Nov 30–Dec 11 | Reproduce + finish | Rerun key results; incorporate feedback and submit before the actual class due date. | Submission-ready class paper, model results and demo. |

If the actual course due date is earlier, compress optional models/genres and move the final
buffer earlier; do not delete freeze, leakage, scorer verification or honest-limit requirements.

### December package

- Class paper with problem/question, literature positioning, source/annotation methods,
  model recipes, paired results, error analysis, limitations and conclusions.
- Frozen source/label/split/context datasheet and reconstruction manifest.
- Verified prediction files, run provenance, metrics, model comparison tables and
  context-by-level figures with uncertainty and explicit denominators.
- Reproduction commands/configs and a small explanation/demo of the two-stage task.
- Transparent fallback/pilot classification if coverage or annotation cannot support stronger claims.

### Publication package

Expand independent validation, literary works/source groups, model families and replication.
Confirm WDSI's official call, year, deadline and paper format with the professor. Release only
permitted materials; no publication or external submission is made merely by completing this spec.

## 15. Acceptance scenarios and traceability

| ID | Scenario | Required observable evidence | Requirements |
|---|---|---|---|
| AC-01 | A source example is proposed. | Source locators reconstruct verbatim target/context; rights/authorship and selection reason exist. | FR-02/03 |
| AC-02 | A fable only expresses a narrator's moral. | It is excluded from request gold or placed in explicit exploratory scope; no invented addressee. | FR-02/04 |
| AC-03 | Wording-only INF functions as a request in dialogue. | Both form and contextual function survive; type is not blindly copied from the legacy label. | FR-04 |
| AC-04 | A calibration test turn has related unreviewed turns. | The whole dialogue group is excluded from untouched test, not only that turn. | FR-06 |
| AC-05 | A target is rendered with less context. | Exact target remains identical and future evidence/gold never enters the input. | FR-07 |
| AC-06 | No compatible mismatch donor exists. | Genuine-context results retain the item; paired mismatch coverage/exclusion is explicit. | FR-07/10 |
| AC-07 | Stage 1 misses a gold indirect request. | End-to-end counts failure; oracle Stage 2 still evaluates its interpretation. | FR-08/09 |
| AC-08 | A model emits malformed output or duplicate IDs. | Schema/coverage validation catches the issue; malformed responses count as errors. | FR-09 |
| AC-09 | Context helps equally at all levels. | Report main effect and absent interaction; do not claim H2 support. | FR-10 |
| AC-10 | L3 is sparse or source-confounded. | No generated replacement items; narrow claims or exploratory/no-estimate H2 decision recorded before test. | FR-03/10 |
| AC-11 | Only Sandy can annotate. | Gold is provisional; no fabricated kappa, independent human baseline or validated-benchmark claim. | FR-05/12 |
| AC-12 | A table is included in the class paper. | Its inputs, endpoint/denominator, run/model/data hashes and reproduction command are traceable. | FR-12 |
| AC-13 | HTML controls are changed offline. | Pipeline, context explanation, workload, roadmap and requirement search work; no external requests or fake results. | NFR-07/08/09 |
| AC-14 | Publication release contains third-party text. | Source-permitted release mode/notices are checked; restricted material is replaced by source references. | FR-14 |

## 16. Risks, fallbacks and unresolved decisions

| Risk | Consequence | Response |
|---|---|---|
| Sparse L3/intent coverage | Interaction cannot be estimated defensibly. | Collect genuine candidates; restrict represented taxonomy; exploratory fallback. |
| Source/level confounding | Genre shortcuts resemble pragmatic ability. | Separate strata; inspect shared support and utterance-only probes. |
| Single-rater gold | Independent reliability/human baseline unavailable. | Report provisional pilot; expand raters for publication. |
| Famous literary passages | Memorization can resemble inference. | Avoid unnecessary identifying titles, audit canonical familiarity, expand lesser-known sources; no contamination-free claim. |
| Future evidence leakage | Artificially easy interpretation. | Prior-only renderer; separate annotation evidence and eligibility flags. |
| Rewrite fact drift | Context effects reflect contradiction errors. | Review flags and report auxiliary-source sensitivity; original gold remains distinct. |
| GPU/API/access constraints | Model grid threatens December deadline. | One feasible encoder/LLM before extras; baseline-first; record recipe limits. |
| Statistical instability | Unreliable mixed-effects estimates. | Freeze supported implementation or descriptive fallback on dev. |
| Timeline or venue ambiguity | Wrong deadline becomes the plan. | Confirm class date now; publication call separately. |
| Explainer mistaken for live tracker | Local simulations imply completed research. | Draft/status labels; no real-run actions or completion percentage. |

| Decision | Topic | Owner | Resolve by | Current position |
|---|---|---|---|---|
| D-01 | Exact December due date | Sandy + course instructor | Before scheduling the final buffer | December priority confirmed; exact date pending. |
| D-02 | Independent second rater | Sandy + professor | Before collecting non-author judgments | Availability and university determination pending. |
| D-03 | Supported intents and required slots | Sandy + professor | After the dev pilot; before freeze | Original six-to-eight-category ambition retained; exact represented subset pending. |
| D-04 | Test size and H2 power | Sandy with statistical advice | Late October; before test scoring | Target 160–240 dialogue / ≥50 groups plus 20–40 literary / ≥10 families; fallback 120 / ≥30 groups. |
| D-05 | Model/version, budget and lab access | Sandy | Before model development and paid runs | Pinned existing encoder environment; checkpoint/API snapshot and cap pending. |
| D-06 | Context and mismatch rendering | Sandy | Before dataset freeze | None/one/full plus separate corrupted mismatch; exact windows pending. |
| D-07 | Statistical implementation | Sandy with statistical advice | On dev; before analysis freeze | Grouped paired contrasts; mixed-effects interaction only if supported. |
| D-08 | WDSI year, call and format | Sandy + professor | Before publication submission planning | WDSI direction confirmed; official year/deadline unverified. |

## 17. Definition of done and guide review

**This specification/guide deliverable is done when:** the master draft consolidates the study;
requirements, work packages and acceptance criteria are traceable; the HTML is self-contained and
faithful to the draft, including full embedded spec text; desktop/mobile keyboard interactions and
workload counts have been checked; original code/data are unchanged; unresolved decisions remain visible.

**The December study is done when:** the course paper and actual model-result package meet FR-12
and the relevant acceptance scenarios, with every downgrade/pilot limitation disclosed.
The HTML/spec alone does not satisfy this condition.

**The publication phase is ready when:** FR-13/14 have evidence, faculty/venue requirements are
confirmed, and a reviewable expanded manuscript/release is prepared. Acceptance is not guaranteed.

### Guide interaction contract

- Select a pipeline step to see purpose, required input, output, dependency, starting status
  and the gate before proceeding.
- Switch the illustrative context demo without changing target wording or displaying fictitious
  model scores/predictions. Teaching text is excluded from the research corpus.
- Adjust item counts and number of evaluated procedures to count rendered conditions/output cells;
  show the formula and distinguish genuine context from corruption controls.
- Select December versus publication roadmap; inspect weekly exit deliverables and unresolved decisions.
- Search/filter requirements by scope and implementation state, with IDs linking to acceptance intent.
- Read or download the full embedded master spec; print a readable snapshot. Local choices do not
  edit the actual protocol, labels or configs.

The specification is a draft. Formal protocol freeze, software implementation and real study
results remain subsequent work.
