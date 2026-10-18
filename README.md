# Pragmatic Intent

**Pragmatic Intent Detection for AI Assistants: An Empirical Study of Conversational Context and Linguistic Ambiguity**

## Research question

> How do conversational context and linguistic ambiguity interact when machine learning and language models infer a user's underlying intent?

The original question remains. The study compares detection of implied requests and recovery of
their intended meaning. Context is varied within an item; request indirectness is annotated by
wording, while ambiguity is measured separately.

## Current plan

The [research plan](docs/research_plan.md) follows the original proposal and targets one deliverable:
a **December 2026 class paper (a computer-science paper) and model results**, conducted through the
Machine & Deep Learning course (re-scoped 2026-10-12).

- Use human-authored MultiWOZ assistant dialogue, with its actual preceding context, for the main experiment.
- Exclude newly generated inputs and invented request ladders from the main benchmark.
- Compare utterance-only, one-turn, full and mismatched context; measure missed requests and
  unsupported intent inference.
- Report the published IndirectRequests set as a separate transfer test, and screened literary
  exchanges (fables, parables) as an optional, separate add-on.
- Prioritize TF-IDF, one encoder, one LLM and a small two-stage hybrid within the class schedule.

See the [collection protocol](docs/source_collection_plan.md), [draft analysis plan](docs/analysis_plan.md)
and [revision report and next steps](docs/research_revision_2026-10-09.md).
Read the consolidated [master specification](specs/001-pragmatic-intent-study/spec.md) or open the
[interactive research guide](specs/001-pragmatic-intent-study/spec-guide.html). The guide works offline
and embeds the version 1.0 draft (it predates the 2026-10-12 re-scope); its controls do not launch
experiments or change research files.

The [original proposal](<docs/Pragmatic_Intent_Detection_Proposal_Plain .pdf>) is preserved.
The [synthetic plan](docs/synthetic_data_plan.md) is historical and inactive.

## Implementation status

The existing DIRECT + MultiWOZ join, annotation tools, calibration rounds 1-3, weak-supervision
Stage 1 trainers, evaluation harness and rewrite fact-drift audit remain available. Round 2
was adjudicated on 2026-10-17. Literary editions (Aesop, King James Bible) are now pinned and have
screening tooling: families, exhaustive candidate proposals and a validated text-free
inclusion/exclusion log ([spec 002](specs/002-literary-sources/spec.md),
[usage](docs/source_collection_plan.md#screening-tooling)). No literary pilot has been screened yet.
Option A (spec 001 v1.2) uses fixed wording rules and MultiWOZ act categories; the historical
spec 003 form/context/reveal pilot is not run. The shared context renderer and committed test
manifest are built ([spec 004](specs/004-context-conditions/spec.md)). Stage 2 act/slot recovery,
separate oracle/routed scoring and the IndirectRequests transfer adapter are now available
([usage](docs/stage2_scoring.md), [spec 005](specs/005-scoring/spec.md)). `auto-v2` is frozen and
provisional pending its fresh L3 spot check; `auto-v1` remains the default. No new model
results are claimed. Execution is tracked in the
[roadmap](specs/001-pragmatic-intent-study/roadmap.md).

The [Stage 1 baseline guide](docs/stage1_baselines.md) covers pinned environments and weak-label
dev experiments on the RTX 5060 (WSL2) or lab RTX 4090. DIRECT variant labels are not human L0-L3
gold. See the [round 2 review](docs/round2_review.md) and [evaluation guide](src/evaluation/README.md).

## Repository layout

~~~text
docs/       research plan, source collection, analysis draft, rubric and revision report
configs/    reproducible Stage 1 model configurations
scripts/    GPU experiment grids
src/        data pipeline, annotation tools, Stage 1 trainers and evaluation
data/       committed ID/label annotations; raw/interim source text stays local
results/    reproducible run logs when experiments are performed
~~~

Data commands and source terms are in [data_sources.md](docs/data_sources.md).
Run the standard-library tests with Python 3.12 from the repository root. They pass in WSL/Linux
and on native Windows (the TOML-fixture path issue was fixed on 2026-10-10):

~~~bash
python -m unittest discover -s tests -t .
~~~

## License

Code is released under the [MIT License](LICENSE). Third-party texts retain their own terms.
Benchmark release will use permitted source text or annotations/source references with
reconstruction instructions.

## Author

Sandy Thomas. Machine & Deep Learning course project, Fall 2026.
