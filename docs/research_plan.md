# Research Plan: Pragmatic Intent Detection for AI Assistants

_Revised 2026-10-09 after Sandy Thomas's 2026-10-08 meeting with Dr. Benjamin Sanders.
First deliverable: a class research paper and model results in December 2026. Publication follows.
The exact class due date and WDSI conference year/deadline remain to be confirmed._

The draft [master specification](../specs/001-pragmatic-intent-study/spec.md) consolidates this plan
with requirements, dependencies and acceptance criteria. Its [offline interactive guide](../specs/001-pragmatic-intent-study/spec-guide.html) explains the full study.

## Research question: retained

The original proposal asks:

> How do conversational context and linguistic ambiguity interact when machine learning and language models infer a user's underlying intent?

The original [proposal PDF](<Pragmatic_Intent_Detection_Proposal_Plain .pdf>) remains the historical
proposal. This revision changes data collection and execution scope, not that question, the
empirical comparison of model families, or the detection/interpretation framing.

**Operationalization:** vary the context shown to each model; annotate request indirectness by
wording and measure ambiguity separately through independent judgments and plausible readings.
Indirectness is not a synonym for ambiguity. Naturally occurring indirectness is an observed
factor, not a randomized manipulation. Context ablation permits within-item comparisons;
cross-level differences can still reflect source, intent, length, or speaker differences.

This revision supersedes the 2026-09-25 existing-data design where they conflict. The DIRECT join,
calibration labels, baselines, and fact-drift audit remain development work. Existing labels and
dev scores do not become a validated benchmark by this revision.

## Incorporating the professor's methods

| Meeting advice | Method in this study | Connection to the original question |
|---|---|---|
| Gather humanities literature, fables, parables, and jokes | Extract actual speaker utterances and preceding source context; screen for a request and textual evidence for its intended meaning. | Adds human-authored pragmatic cases without generating inputs. |
| Avoid synthetic data bias | Exclude LLM-generated inputs, invented contexts and researcher-written request ladders from the main benchmark. Preserve original source text. | Reduces generator artifacts while retaining context ablations. |
| Name the behavior | Use pragmatic inference, indirect speech acts and, where applicable, conversational implicature. | Distinguishes implied requests from morals, motives, or factual meaning. |
| Quantify performance and assess existing research | Use two-stage metrics and context-by-indirectness comparisons; conduct a bounded literature review. | Supplies evidence without replacing the study with a survey. |
| Compare single- and multi-layer implications | Annotate an exploratory evidence chain independently of request form. | Adds a difficulty measure without defining L3 by context need. |
| Consider negative/contradictory cases | Include real informing, refusal and non-request examples; audit mismatches and rewrite drift. | Measures over-inference as well as missed requests. |

The handwritten negative-example line is ambiguous; the notes PDF says it was normalized.
Negative controls are a recommendation here, not evidence that the professor mandated a
separate contradiction model.

## Data design

Follow [source_collection_plan.md](source_collection_plan.md). Collect two source strata together,
but report them separately:

1. **Assistant-dialogue stratum: main December experiment.** Human-authored MultiWOZ target turns
   with actual preceding dialogue. DIRECT's human-written rewrites are a separately identified
   auxiliary source for weak training and paired development diagnostics. They are elicited
   paraphrases, not spontaneous conversation or human L0-L3 gold.
2. **Literary-dialogue stratum: collection pilot and held-out transfer evaluation.** Addressed
   exchanges from pinned editions of Aesop, parables, and other human-authored works; include jokes
   only where authorship, rights and context are clear. Expand into a powered replication after
   the class. Do not pool literary and assistant scores to imply general assistant performance.

Literary inputs remain the original character's exchange. Infer the request to the original
addressee; do not invent an assistant scenario. Map to the assistant taxonomy only where the
function fits. An out-of-scope request is still a request, not a negative.

**Starting targets, not collected counts or power guarantees:** screen a 60-candidate development
pilot (about 40 dialogue, 20 literary). Aim for 160-240 dialogue test utterances across at least
50 independent dialogue groups, plus 20-40 literary items across at least 10 story/episode families.
A smaller course fallback is 120 dialogue utterances across at least 30 groups plus a documented
literary pilot. Development/pilot groups are additional and never enter test. Context variants
do not create independent examples.

Aim for 25-40 requests per L0-L3 level and enough genuine negatives to estimate false positives.
Set exact quotas after the pilot and before test collection/scoring. Do not manufacture L3 or
rewrite missing intents into existence. If rare levels or group coverage cannot support inference,
report H2 as exploratory or not estimable. Reduce represented intent categories rather than
claiming all eight proposed categories are covered.

## Tasks and context conditions

**Stage 1:** identify direct request, indirect request, or no request. Annotate request function
in original full context separately from wording. For validated requests, L0 maps to direct and
L1-L3 to indirect. Keep informing and social non-requests as separate metadata/slices.
Never automatically map the historical wording-only INF label to a contextual non-request.
Requests with undecidable form remain in request-status analysis but leave level-based
confirmatory analysis. Unresolved full-context meanings form an ambiguity challenge set.
No historical labels are silently remapped.

**Stage 2:** recover supported intent category, applicable required key slots and a concise direct
paraphrase. Use a bounded supported intent set for December. MultiWOZ domains/acts suggest labels,
but do not establish gold speaker intent automatically.

| Condition | Input |
|---|---|
| none | Target alone, with fixed source-grounded speaker/addressee identifiers where needed. |
| one | Identical target plus its last preceding source turn/context unit. |
| full | Identical target plus the predefined preceding source window. |
| mismatched | Identical target plus unrelated same-stratum, same-split context matched on length and format. |
| mismatched_one | Optional one-unit donor control, already supported by the DIRECT loader. |

Exclude later replies, story endings, morals, commentary, gold labels and direct gold paraphrases
from model input. Record later evidence separately for annotation; flag items whose interpretation
depends on information unavailable in full context. Mismatches are deliberately corrupted inputs,
not authentic alternative conversations. Report them separately as robustness controls, without
claiming historical gold is the true intent in a newly invented exchange.

## Hypotheses and analysis

| ID | Retained hypothesis | Role |
|---|---|---|
| H1 | Performance falls as request indirectness increases. | Replication, not a novelty claim. |
| H2 | Context helps more as indirectness increases. | Primary interaction of interest. |
| H3 | Context benefit differs by model family. | Secondary; December's small panel supports descriptive comparison. |
| H4 | Detection degrades more slowly than interpretation. | Compare on identical gold indirect-request items; show oracle and routed Stage 2. |
| H5 | Some intent categories are systematically harder. | Exploratory, subject to coverage. |

The [analysis plan](analysis_plan.md) is a **draft**, not a completed preregistration. Freeze sample,
endpoints, exclusions, statistical implementation and model settings before reported test runs.
Resolve feasibility using development data, not test performance.

Measure ambiguity with independent utterance-only and full-context judgments: agreement,
uncertainty and supported alternative readings. Disagreement is a proxy, not proof of intrinsic
ambiguity; missing-context uncertainty differs from full-context uncertainty. If only Sandy labels,
mark independent agreement and the human baseline unavailable. LLM review does not substitute
for independent human judgments. Treat clarification requests as exploratory: their dependence on
prior discourse can mechanically favor context.

## Model development

Retain the existing TF-IDF/logistic-regression and encoder code. Its **direct_variants_v1** weak
supervision policy remains unchanged. It trains from DIRECT rewrites and scores dev, not the new
contextual gold schema. Human-written rewrite training is compatible with excluding LLM-synthetic
inputs, while its source and label limitations remain visible.

Prioritize for December:

1. Majority and utterance-only TF-IDF, followed by context-aware TF-IDF.
2. One encoder family in the pinned environment; a second only after complete results from the
   first. Keep effective batches, seeds and optimization comparable across conditions.
3. One instruction-tuned LLM with a fixed structured-output prompt for both tasks. Choose its
   dated checkpoint/API version and budget on dev.
4. A small hybrid routing predicted indirect requests from the encoder to that Stage 2 LLM.
   Also score Stage 2 on all gold indirect requests to expose routing failures.

Build an adapter/scorer for contextual gold before claiming these trainers evaluate the revised
benchmark. Six-way form classification, weak rewrite classification and contextual request
detection are distinct tasks. Literary test families stay out of training and few-shot prompts.
Later literary-training comparisons require independent train/dev works and a new frozen protocol.
This documentation revision authorizes neither new paid model runs nor deployment.

## October-December execution schedule

These are planning windows, not a confirmed university deadline. Move the final buffer earlier
if the actual class due date precedes December 11.

| Window | Work | Exit evidence |
|---|---|---|
| Oct 12-18 | Adjudicate round 2 under rubric v2; screen the 60-candidate pilot; confirm due date, second reviewer, GPU/API access. | Source inventory, exclusion log, provisional taxonomy. Pilot is dev-only. |
| Oct 19-25 | Independent pilot annotation; revise form/function supplement; inspect level/genre coverage; run existing weak baselines on dev. | Agreement/feasibility report or explicit single-rater limitation; training policy. |
| Oct 26-Nov 1 | Collect untouched source groups; freeze gold policy, splits, contexts and analysis settings. | Manifest/hashes, datasheet and frozen analysis plan; no test scores. |
| Nov 2-8 | Implement contextual adapter and Stage 2 scorer; train TF-IDF and one encoder; develop LLM prompt on dev. | Tested scoring, reproducible dev outputs, checkpoint/config pins. |
| Nov 9-15 | Freeze models/prompts; run the core context grid and hybrid on held-out data. | Complete predictions, seeds, provenance, runtime/cost log. |
| Nov 16-22 | Analyze paired contrasts, ambiguity, negatives and errors; audit story memorization risks. | Tables, confidence intervals and explicit inferential limits. |
| Nov 23-29 | Write class paper with data selection, methods, model results and limitations. | Full draft, figures and reproduction instructions. |
| Nov 30-Dec 11 | Reproduce key results, incorporate professor feedback if available, finalize before actual due date. | Submission-ready paper, model results and demo. |

**Scope rule:** drop extra models, QLoRA, large literary quotas and added genres before sacrificing
genuine context ablation, clean held-out groups or negative controls. If independent labeling is
unavailable, deliver a clearly labeled pilot with provisional labels, not a validated benchmark.

## Literature review and publication

Treat the professor's question about worldwide hallucination accuracy in 2015-2025 as a bounded
background/scoping review. Extract task-specific definitions, datasets, model versions, metrics
and denominators; do not average incomparable results into a worldwide accuracy number.
Earlier NLG studies need not be contemporary LLM studies. Keep 2026 competitors in a separate update.

Verified starting points (2026-10-09; not an exhaustive review):

- [DIRECT, Takayama et al. (2021)](https://aclanthology.org/2021.findings-emnlp.170/): human pragmatic paraphrases and dialogue history.
- [Circa, Louis et al. (2020)](https://aclanthology.org/2020.emnlp-main.601/): indirect answers; its labels are not request-function gold.
- [Hu et al. (2023)](https://aclanthology.org/2023.acl-long.230/): human/model pragmatic comparison.
- [Ji et al., hallucination survey](https://doi.org/10.1145/3571730): generation-faithfulness background, not this task's error rate.
- [Ma et al. (2025)](https://aclanthology.org/2025.acl-long.425/): pragmatics datasets/evaluation map.
- [Mannekote et al. (COLING 2025)](https://aclanthology.org/2025.coling-main.696/): synthetic indirect requests; related work, excluded from the human-only main benchmark.
- [DRInQ (2026)](https://arxiv.org/abs/2605.24267): controlled context variation for implicature.
- [READI (2026)](https://arxiv.org/abs/2608.30270): graded indirect speech acts with multimodal context.

The proposed contribution is the request-focused context-by-indirectness comparison, detection
versus interpretation, and transfer to screened literary exchanges. Full-paper reading and an
updated search must establish novelty; these starting sources do not prove an unfilled gap.

WDSI is Sandy's intended publication direction. The meeting summary says WDSI 2027/August 2026;
the handwriting and notes PDF say August 2027/March 2028. Sandy confirmed December's class
paper/results come first but did not resolve the conference year. Confirm the official call and
format with the professor before setting submission dates; none of these dates is verified.

After December, expand independently annotated groups and literary diversity, add model families,
strengthen ambiguity/depth annotation and run a powered replication. Release source-permitted
text or ID/offset annotations with reconstruction instructions. Successful literary intent
classification does not demonstrate subsequent human behavior prediction or reliable autonomous action.

## Compute and reproducibility

Continue CPU development and small encoder runs on the RTX 5060 through WSL2; use the lab RTX 4090
for reported GPU runs when available. Follow [stage1_baselines.md](stage1_baselines.md) and the
pinned uv.lock. Record seed, dataset/config hashes, checkpoint revision, Git commit and machine.
Keep one recipe/machine per reported model and log quantization rather than combining different
settings under one score. This revision does not launch training or change dependency pins.
