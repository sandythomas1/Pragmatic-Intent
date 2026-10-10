# Research Revision and Next Steps

_2026-10-09. Prepared for Sandy Thomas following the 2026-10-08 meeting with Dr. Benjamin Sanders._

## Outcome

**Keep the original research question; change how the evidence is collected.** The December 2026
class paper and model results are the first milestone. WDSI publication remains the longer-term
direction, with the conference year and official deadline unconfirmed.

The question from the original proposal remains:

> How do conversational context and linguistic ambiguity interact when machine learning and language models infer a user's underlying intent?

The professor's source-gathering advice supports this question when literary examples contain
actual communicative intent. Gather addressed dialogue from human-authored sources, preserve its
wording/context and evaluate how much preceding context helps models recover the request.
Do not substitute moral extraction or general human-behavior prediction for request interpretation.

## Context recovered

Reviewed the repository's original three-page proposal PDF, research plan, synthetic-plan decision
history, data-source/provenance policy, rubric v2, round-2 review, Stage 1 baseline guide and
evaluation/audit documentation. Reviewed the supplied handwritten image, the one-page research
notes PDF and Sandy's meeting summary. The PDFs were text-extracted and their pages visually checked.

Existing work includes the DIRECT/MultiWOZ join, calibration rounds 1-3, weak-supervision
baselines and fact-drift checks. Round 2 remains unadjudicated; the reference suggestions are not
a second independent annotation. No training results are invented or promoted from dev to test.

The project has no checked-in project AGENTS.md or CLAUDE.md at this revision's starting point.
Shared workspace instructions and relevant engineering/research memory provided context.
The initial sandbox could not start repository commands or perform edits. Approved shell access
enabled repository/PDF reads and documentation writes; no permissions or security settings were
changed. This file and the linked plans provide a handoff for future Codex or Claude sessions.

## What changed

| File | Change |
|---|---|
| [research_plan.md](research_plan.md) | Replaced conflicting historical phase instructions with one current plan; retained question/H1-H5; added source strata and October-December execution windows. |
| [source_collection_plan.md](source_collection_plan.md) | Added source inventory, screening, evidence requirements, separate form/function labels, ambiguity/depth annotation and source-group leakage controls. |
| [analysis_plan.md](analysis_plan.md) | Added a clearly unfrozen draft with endpoints, denominators, paired contrasts, dependence structure and freeze checklist. |
| [README](../README.md) | Updated question, December priority, active methods and actual implementation status. |
| [data_sources.md](data_sources.md) | Distinguished historical downloaded-source catalogue from current roles and new literary candidates. |
| [annotation_guidelines.md](annotation_guidelines.md) | Preserved v2 and added a notice explaining the new contextual supplement still to be developed. |
| [synthetic_data_plan.md](synthetic_data_plan.md) | Marked historical generation/hand-authored input design inactive under the revised policy. |
| [stage1_baselines.md](stage1_baselines.md) | Clarified that existing trainers remain weak-label dev tools and that a draft analysis file is not a frozen protocol. |

The original proposal PDF, dataset manifest/pins, annotations, model code, configs and dependency
lockfile are preserved. Literary ingestion, contextual annotation adapters, Stage 2 scoring,
new data collection and model experiments remain next steps, not completed work.

## Professor advice: retained with task boundaries

Humanities literature is a collection source, not merely background reading. Aesop's dialogues
and the water-to-wine exchange are candidates for screening. Their interpretations remain
unlabeled until source/evidence review and independent judgments. A story's ending, moral or
published explanation can inform an audit but must not leak into model input.

Use single/multiple implication steps as an exploratory annotated evidence-chain feature, separate
from indirectness and ambiguity. Use authentic non-requests and reviewed contradiction controls
to measure unsupported inference. The ambiguous handwritten negative-example wording does not
establish a requirement for a separate contradiction model.

The professor's R1 about hallucination research from 2015-2025 is useful as a background review
starting point. It is too broad to replace this project's empirical question: different tasks use
different definitions and denominators. A more useful review objective is:

> Identify how prior studies evaluate pragmatic inference and unsupported interpretation, and which methods permit testing context-by-indirectness effects in request detection and interpretation.

Search ACL Anthology, primary paper repositories and publisher records for 2015-2025, with a
separate 2026 competitor update. Log search strings/date, inclusion/exclusion counts, and backward/
forward citation checks. Include work with a defined pragmatic or faithfulness task and an
inspectable evaluation protocol. Extract task, source/authorship, context manipulation, model/version,
gold procedure, metric/denominator, uncertainty and relevance. Do not report a worldwide pooled
hallucination accuracy. The verified starting sources are linked in the research plan; this is
a search protocol and initial map, not a completed systematic review.

## Immediate next steps, in order

1. **Confirm the exact December due date.** Use the paper/results deadline to place the final
   reproduction and writing buffer. Separately confirm WDSI's official year, call and format.
2. **Finish calibration adjudication.** Apply v2 to round 2 without altering initial labels;
   document why any final labels change.
3. **Screen a dev-only 60-candidate pilot.** About 40 original dialogue and 20 literary exchanges.
   Pin editions, log every rejection and inspect indirectness/request/genre coverage.
4. **Pilot the contextual annotation supplement.** Separate wording from full-context function,
   evidence, supported interpretation and ambiguity. Obtain an independent reviewer if possible;
   check university requirements before recruiting non-author participants.
5. **Make a feasibility decision by late October.** Set attainable test quotas, supported intents,
   model/budget choices and whether H2 can be confirmatory. Do not force missing L3 examples.
6. **Freeze new test groups and the analysis plan.** Preserve official dialogue splits, exclude
   whole previously inspected calibration dialogues and group literary retellings/editions.
7. **Implement the missing adapter/scorers.** Extend beyond six-way form and weak rewrite labels;
   support structured Stage 2 targets and oracle versus routed evaluation. Verify on dev.
8. **Run the December model panel.** TF-IDF, one encoder, one LLM and a small hybrid across genuine
   context conditions; retain mismatch as a separate corruption control.
9. **Write results and limits by late November.** Include uncertainty, false positives, literal
   readings, unsupported additions, source-selection bias and canonical-story familiarity.
10. **Expand for publication after the class.** More independent annotators/source groups, literary
    diversity and model families; a powered replication and source-compatible release.

The primary December target is 160-240 dialogue test utterances across at least 50 groups and
20-40 literary transfer items across at least 10 story families. The smaller fallback is 120
dialogue items across at least 30 groups plus a literary pilot. These are proposed collection goals,
not existing data or statistical power guarantees. A single-annotator study must be labeled a
pilot; it cannot claim independent agreement or a human baseline.

## Suggested explanation to the professor

I want to keep my original question about how conversational context and linguistic ambiguity
affect models' inference of underlying intent. I will incorporate your advice by collecting
human-authored dialogue and selected literary exchanges, including fables and parables, instead
of generating the main benchmark. I will distinguish a speaker's implied request from a story's
moral and test identical utterances with different amounts of preceding context.

For December, I will prioritize a manageable annotated sample and reproducible model comparisons.
The hallucination literature review will help define unsupported intent inference and position
the study. After the class, I want to expand the corpus and validation for publication at WDSI.

## Dates and verification record

The typed meeting summary lists WDSI 2027/August 2026; the handwritten image and notes PDF list
August 2027/March 2028. Sandy confirmed December's class deliverable takes priority but did not
resolve the conference year. No contradictory date has been silently treated as an official deadline.

Verification is recorded below after the final document/link/diff checks. No new dataset
acquisition, GPU training, paid API use, human recruitment or paper submission occurred in this
documentation revision.

**Verification (2026-10-09):**

- All 116 existing tests passed under WSL Ubuntu with the already-installed Python 3.12. No dependencies were installed.
- Native Windows Python 3.12: 115 passed, one error in the unchanged RunnerTest temporary TOML fixture. It inserts an unescaped Windows path into a quoted TOML string, causing Invalid hex value. The same suite passes with Linux paths; no source/test fix was included in this documentation task.
- Local Markdown links resolve; UTF-8 files decode; the original question is preserved verbatim in the README, research plan and this report.
- Git diff whitespace checks passed. Source code, tests, configs, data/annotations, proposal PDF, manifest and dependency pins are unchanged. PDF review images remain in ignored outputs/research-review/.
- Publication timing remains provisional. Dataset collection, annotation validation, contextual adapters and model experiments are future work.

This revision is committed on research/human-sources-december-plan, based on the existing annotation/round3-rubric-v2 branch so its work is retained. The commit and remote synchronization are checked before delivery; no pull request or merge is part of this task.
