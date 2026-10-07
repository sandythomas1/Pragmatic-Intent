# Pragmatic Intent

**Pragmatic Intent Detection for AI Assistants: An Empirical Study of Conversational Context and Linguistic Indirectness**

People rarely ask AI assistants for things directly. "It's freezing in here" can be a request to turn
up the heat, and "I have an interview tomorrow and haven't practiced" can be a request for help
preparing. This project measures how well machine-learning and language models recover what the user
*means*, and how that ability depends on:

- **Degree of indirectness.** Utterances range from direct requests ("Turn the heat up") to
  conventionally indirect ones ("Can you turn the heat up?") to strong and mild hints.
- **Amount of conversational context.** Models see the utterance alone, one prior turn, the full
  dialogue history, or a mismatched history from a different conversation.

## Research question

> How do conversational context and degree of linguistic indirectness interact when models detect and
> interpret a user's underlying intent?

The central hypothesis is that context helps more as requests become less explicit.

## Approach

- **Two-stage task.**
  - Stage 1 (detection): is the user making a direct request, an indirect request, or no request?
  - Stage 2 (interpretation): for indirect requests, what is the underlying request?
- **Controlled benchmark.** About 8 assistant-intent categories × 4 indirectness levels (grounded in
  the CCSARP request-strategy scale) × 4 context conditions. It includes contrastive items where the
  same utterance is or isn't a request depending on context. Test items are human-validated.
- **Model comparison.** A classical baseline (TF-IDF + logistic regression), fine-tuned transformer
  encoders, prompted LLMs (open-weight and API), and a two-stage hybrid pipeline.
- **Analysis.** A mixed-effects test of the context × indirectness interaction, a human baseline,
  per-intent difficulty, and error analysis.

## Status

**Data pipeline and evaluation development.** DIRECT is joined to MultiWOZ 2.1;
annotation sampling, labeling and export are implemented. Calibration round 1 has
15 labels and round 2 has 30 completed labels, with adjudication pending. See the
[round 2 review](docs/round2_review.md) for proposed corrections and the coding path,
and the [evaluation harness](src/evaluation/README.md) to run the first development
baseline. The [research plan](docs/research_plan.md)'s existing-data revision governs
the current design; the synthetic benchmark described above remains parked.

**Stage 1 baselines are ready to run** on the RTX 5060 (WSL2) or the lab RTX 4090.
They use a pinned `uv` environment (torch 2.11 + CUDA 12.8). Training uses explicit
weak labels from DIRECT's train split, and scoring is on dev under every context
condition, with paired context contrasts. The TF-IDF and cross-encoder trainers are
included. See [Stage 1 baselines](docs/stage1_baselines.md) for the policy, setup and
run order. No model has been trained yet.

## Repository layout

The layout will grow as the phases land:

```text
docs/       research plan, analysis plan, annotation guidelines
configs/    experiment configs (one config = one reproducible run)
scripts/    experiment grids for the GPU machines
src/        data pipeline, annotation tools, Stage 1 trainers, evaluation harness
data/       local datasets (raw sources are not committed; see their licenses)
results/    run logs (JSONL) and figures
```

## License

The code is released under the [MIT License](LICENSE). The benchmark data will be released
separately under a license compatible with its source datasets.

## Author

Sandy Thomas. Started as a Machine & Deep Learning course project, Fall 2026.
