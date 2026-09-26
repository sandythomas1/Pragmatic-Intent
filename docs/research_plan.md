# Research Plan: Pragmatic Intent Detection for AI Assistants

_Created 2026-09-23 from the Fall 2026 CSCI 4220 proposal. Goal: course report in Week 10, then a
workshop/SRW paper submission._

## Design revision (2026-09-25): existing-data path

_Approved by the user. Where this section conflicts with the rest of this plan, this section wins.
The synthetic benchmark is parked ([`synthetic_data_plan.md`](synthetic_data_plan.md)). Data details
are in [`data_sources.md`](data_sources.md)._

**New design.**
- **Core data:** DIRECT's same-turn triples (original / direct / indirect version of each MultiWOZ
  user turn), with context from MultiWOZ 2.1 joined on `dialogue_id` + `turn_index`. All 71,498 rows match.
- **Levels:** the user hand-labels CCSARP levels L0–L3 on a sample, from the utterance alone.
- **Stage 1:** direct vs. indirect. `no_request` covers only genuine non-requests (thanks and
  closings; about 16% of targets by user acts).
- **Stage 2:** intent labels come from MultiWOZ domain + user dialogue acts.
- **Context:** none / one prior system turn / full history / a length-matched mismatched history from
  a same-split dialogue with no shared domain. Contexts are derived at load time
  (`src/data/build_direct_dataset.py`).
- **Splits:** MultiWOZ's official train / val (as dev) / test, grouped by dialogue.
- **Later:** a small hand-written contrastive set is an optional add-on. Hypotheses H1–H5 are unchanged.

| Original item | Status |
|---|---|
| Decisions 1–2 (indirectness by CCSARP form; ambiguity measured) | **Unchanged.** Indirectness is now labeled on existing utterances, not written as ladders. |
| Decision 3 (3-way Stage 1) | **Changed.** Direct vs. indirect, with `no_request` only for genuine non-requests. |
| Decision 4 (contrastive items in every scenario) | **Superseded.** Now an optional add-on. |
| Decision 5 (four context conditions incl. mismatched) | **Unchanged.** Adds a mismatched control for the one-turn condition. |
| Decision 6 (split by scenario) | **Changed.** Split by dialogue (MultiWOZ official split). |
| Decision 7 (generator-family bias) | **Mostly moot.** DIRECT is human-written; this applies again only to LLM-written add-ons. |
| Phase 0 (taxonomy, rubric) / Phase 1 (κ pilot) | **Changed / unchanged.** Intents = MultiWOZ domains + acts. The level rubric and a second labeler for ~50 items are still needed. |
| Phase 2 (build benchmark) | **Superseded** by the DIRECT + MultiWOZ join. |
| Phases 3–7 (harness, experiments, analysis, report, release) | **Unchanged.** The release can hold only code + labels (IDs, levels), because DIRECT's text can't be redistributed. |

**Main risk:** DIRECT already ran a binary history ablation, and history barely helped. Novelty rests
on the graded context × level interaction and the mismatched control.

## Central question

How do **conversational context** and **degree of indirectness** *interact* in determining whether
models can (1) detect that a user is making an indirect request and (2) recover the request they
intend?

Hypotheses (freeze these in `docs/analysis_plan.md` before running experiments):

| # | Hypothesis | Role in the paper |
|---|------------|-------------------|
| H1 | Accuracy falls as indirectness increases. | Replication. READI (2026) already reports this for multimodal ISAs, so it is not the contribution. |
| H2 | Context helps more as indirectness increases (context × indirectness interaction). | **Headline claim.** |
| H3 | The size of the context benefit differs by model family (classical / fine-tuned encoder / LLM). | Main secondary result. |
| H4 | Detection (is there a request?) degrades more slowly than interpretation (what is it?). | Justifies the two-stage framing. |
| H5 | Some intent categories are systematically harder. | Exploratory. |

A result that contradicts a hypothesis is still a finding, as long as the analysis plan was written first.

---

## Design decisions to lock in Phase 0

Reviewers will check these first.

1. **Manipulate indirectness, not ambiguity.** The proposal title and research question say
   "linguistic ambiguity", but the variable you manipulate is indirectness. These are different
   things: "Could you turn the heat up?" is indirect but not ambiguous. Treat indirectness as the
   manipulated variable. Treat ambiguity as something you *measure*, using annotator disagreement.
2. **Define indirectness by form, not by whether context is needed.** If the top level is defined
   as "only clear from context", then H2 is true by definition. Instead, use the CCSARP
   request-strategy scale (Blum-Kulka, House & Kasper, 1989), which you can annotate from the
   utterance alone:

   | Level | CCSARP strategy | Device example | Advice example |
   |-------|-----------------|----------------|----------------|
   | L0 | Direct: imperative or want statement | "Turn the heat up." | "Help me prep for my interview." |
   | L1 | Conventionally indirect: query-preparatory | "Can you turn the heat up?" | "Could you help me prep for my interview?" |
   | L2 | Strong hint: mentions an element of the request | "The thermostat's set really low." | "I have an interview tomorrow and haven't practiced." |
   | L3 | Mild hint: no reference to the request itself | "I can see my breath in here." | "Tomorrow's a big day and I'm so not ready." |

   Then measure context-dependence empirically: annotators label every test item both with and
   without context.
3. **Make Stage 1 labels 3-way:** `direct_request` / `indirect_request` / `no_request`. A binary
   "indirect vs. not" label puts direct requests and small talk in the same class.
4. **Include contrastive items.** Every scenario needs the *same utterance* in one context where
   it is a request and another where it is not, or where it maps to a different intent. Without
   these, an utterance-only model can solve most items and the context ablation shows little.
5. **Use four context conditions:** none, 1 prior turn, full history, and **mismatched** (history of
   the same length taken from a different scenario). The mismatched condition separates "relevant
   context helps" from "more tokens help".
6. **Split by scenario.** Keep every variant of a scenario in the same split. Random splits leak
   near-duplicates between train and test.
7. **Don't evaluate only the model family that generated the data.** If an LLM family writes
   candidate data, also evaluate other families. Keep a human-written subset and report its
   results separately.

---

## Phases

### Phase 0: Lock the design (Week 1)
- [ ] Resolve decisions 1–7 above.
- [ ] Write `docs/analysis_plan.md` with the hypotheses, metrics, statistical tests, and what counts as support. Date it. This is a lightweight pre-registration.
- [ ] Read the close competitors (see Related work) and write one "how we differ" paragraph for each.
- [ ] Set up the repo skeleton and a pinned environment that runs on both machines (see Compute).
- **Exit criteria:** taxonomy v1 (8 intents with definitions and boundary examples), indirectness rubric v1, analysis plan, and a working environment on both GPUs.

### Phase 1: Guidelines pilot (Weeks 1–2)
- [ ] Hand-write 5–10 seed scenarios per intent across L0–L3, plus contrastive `no_request` versions.
- [ ] Have a second person label about 50 items blind, using only the guidelines. Compute Cohen's κ for level and for intent.
- [ ] Revise the guidelines wherever the two of you disagreed.
- **Exit criteria:** κ of roughly 0.6 or higher on the pilot. If agreement is lower, merge categories or levels before scaling up. Scaling noisy labels wastes the rest of the project.

### Phase 2: Build the benchmark (Weeks 2–4)
- [ ] **Existing data:** DIRECT (training and transfer; note it uses MultiWOZ domains), IndirectRequests, Circa, and CLINC150/MASSIVE for direct seed utterances. Record the license and provenance of every source.
- [ ] **Controlled set:** scenario templates → LLM-assisted generation of contexts and L0–L3 versions → automatic filters (dedupe, length, intent keyword appearing in L3) → human review.
- [ ] **Size (adjust after the pilot):** about 8 intents × 40 scenarios ≈ 320 scenarios. With 4 levels plus contrastive items, that is about 1,500 utterances, each run under 4 context conditions. Aim for at least 30 test items per intent × level cell.
- [ ] Double-annotate the whole test set, or at least 25% of it. Report agreement and adjudicate disagreements.
- [ ] Collect human judgments with and without context. These give you both the empirical context-dependence measure and a **human baseline**.
- [ ] Freeze the test set: version it, hash it, and write a datasheet (Gebru et al.).
- [ ] **IRB:** if anyone other than you provides judgments (for example, classmates as the human baseline), ask your professor or the IRB office whether review is needed *before* collecting.
- **Exit criteria:** frozen train/dev/test splits grouped by scenario, a datasheet, and agreement statistics.

### Phase 3: Evaluation harness and baselines (Weeks 4–5)
- [ ] Build the harness first. It should take predictions, gold labels, and metadata, and report metrics sliced by context × indirectness × intent with bootstrap CIs.
- [ ] Baselines: majority class; TF-IDF + logistic regression (utterance-only and with context); utterance-only DeBERTa-v3 and RoBERTa.
- [ ] **Artifact probe:** if the utterance-only model does well on L3 or on contrastive items, the data has surface shortcuts (as with hypothesis-only baselines in NLI). If so, go back to Phase 2.
- **Exit criteria:** a baseline table and first degradation curves, with the artifact probe passed.

### Phase 4: Main experiments (Weeks 5–8)
- [ ] **Context-aware encoders:** a `[context] </s> [utterance]` cross-encoder under all 4 context conditions, with at least 3 seeds (5 if affordable).
- [ ] **Open LLMs:** 2–3 open-weight instruct models (7–14B, bf16, served with vLLM), zero-shot and few-shot, using the same prompt template for every model.
- [ ] **Closed LLMs:** 1–2 API models as a reference point. Pin dated model versions, use temperature 0, and log every prompt and output.
- [ ] **Two-stage hybrid:** the Stage 1 classifier routes predicted `indirect_request` items to Stage 2 LLM interpretation. Compare it against an end-to-end LLM.
- [ ] **Stage 2 evaluation:**
  - Primary metric: accuracy of the predicted intent category (and key slot). This is objective.
  - Secondary metric: quality of the free-text paraphrase, judged by humans on a sample and by an LLM judge that you validate against those human judgments.
  - Don't lead with BLEU or ROUGE.
- [ ] Optional: a QLoRA-fine-tuned 7–8B model.
- [ ] Keep every run config-driven and reproducible with one command. Append each result to `results/*.jsonl` with the git hash, seed, model version, and GPU.
- **Exit criteria:** the full results grid. Report nothing that can't be regenerated from a config.

### Phase 5: Analysis (Weeks 8–9)
- [ ] **Primary test (H2):** mixed-effects logistic regression,
      `correct ~ indirectness * context * model + intent + (1 | scenario)`
      (lme4 in R, or pymer4/statsmodels). The interaction coefficient is the headline number.
- [ ] Compare models pairwise with McNemar's test or a paired bootstrap, and correct for multiple comparisons.
- [ ] **Headline figure:** accuracy vs. indirectness level, one line per context condition, one panel per model family, with the human baseline as a reference line.
- [ ] **Error analysis:** hand-code 150–200 errors into a small taxonomy: literal reading, wrong intent, missed cue in context, over-inference on `no_request` items, and so on.
- **Exit criteria:** a draft results section that answers every hypothesis, including the ones that fail.

### Phase 6: Course deliverable (Week 10)
- [ ] Technical report, clean repo, README with reproduction commands, and a presentation/demo.
- [ ] Write the report in the ACL template from the start (4 pages for a short paper, 8 for a long one, plus Limitations). That way Phase 7 is a revision, not a rewrite.

### Phase 7: Publication push (after the course, about Dec–Feb)
- [ ] Ask your professor to advise or co-author. A faculty co-author makes the paper stronger and improves its chances.
- [ ] Strengthen what reviewers will flag: more annotators on the test set, one more model family, and robustness to prompt paraphrases.
- [ ] Write Limitations and Ethics sections (English only, synthetic data, annotator pool). ACL venues require them.
- [ ] Release the dataset (Hugging Face, with the datasheet and a license), the code (GitHub), and a preprint (arXiv).
- [ ] **Venue:** the ACL/NAACL/EMNLP Student Research Workshop is built for student-first-author papers and has offered pre-submission mentoring. A dialogue or pragmatics venue (SIGDIAL, or a pragmatics/implicit-language workshop) is the alternative. Deadlines set the Phase 7 timeline, so check aclrollingreview.org and the 2027 conference sites early.

---

## Related work to add (found 2026-09-23)

- **READI:** "Read the Room, Read the Image: Understanding Indirect Speech Acts in Multimodal Visual Contexts", arXiv:2608.30270 (Aug 2026). Uses graded indirectness grounded in pragmatic theory and reports performance falling as indirectness rises. **This is the closest competitor on H1.** Position against it: their context is visual; ours is dialogue context, with assistant intents, detection vs. interpretation, a model-family comparison, and the interaction effect.
- **DRInQ (your ref [5]):** verified as an ACL 2026 long paper, arXiv:2605.24267. It holds the surface form of a question fixed and varies context, which is the same contrastive idea. Differences: it covers questions only, and studies implicature rather than assistant requests.
- "Evaluating Large Language Models on Understanding Korean Indirect Speech Acts", arXiv:2502.10995. An LLM evaluation of indirect speech acts.
- Hota & Jokinen, "Implicature in Interaction: Understanding Implicature Improves Alignment in Human-LLM Interaction", arXiv:2510.25426.
- "Is the Pope Catholic? Yes, the Pope is Catholic. Generative Evaluation of Non-Literal Intent Resolution in LLMs", arXiv:2405.08760. Relevant to Stage 2 evaluation.
- Circa: Louis, Roth & Radlinski, "'I'd rather just go to bed': Understanding Indirect Answers", EMNLP 2020.
- Blum-Kulka, House & Kasper (1989), *Cross-Cultural Pragmatics: Requests and Apologies*. The source of the CCSARP indirectness scale.
- Gururangan et al. (2018) and Poliak et al. (2018) on annotation artifacts and hypothesis-only baselines. These motivate the utterance-only artifact probe.
- **Citation fix:** ref [3] (Mannekote et al.) was published at COLING 2025. Cite that instead of the arXiv version.

---

## Compute

Rule: **develop on the RTX 5060 (WSL2), run all reported experiments on the RTX 4090.**

| Workload | RTX 5060 (8 GB, WSL2) | RTX 4090 (24 GB) |
|----------|-----------------------|------------------|
| Data pipeline, TF-IDF + LR | Yes (CPU) | Not needed |
| DeBERTa/RoBERTa-base fine-tuning | Yes | Yes, faster |
| Large encoders with multi-turn context (~512 tokens) × 3–5 seeds | Only with gradient checkpointing and tiny batches; slow | Yes |
| 7–8B LLM inference in bf16 (~16 GB of weights) | No | Yes (vLLM) |
| 7–8B LLM inference in 4-bit | Works, but quantization becomes a confound | Not needed |
| 13–14B LLM inference | No | 8-bit/4-bit only (bf16 needs ~28 GB) |
| QLoRA fine-tuning of a 7–8B model | Barely, and only for short sequences | Yes |
| Closed-model APIs | No GPU needed | No GPU needed |

Rules:
1. Each reported number for a given model comes from one machine and one config. Don't mix
   quantized and unquantized runs of the same model.
2. Use the same pinned environment on both machines (a uv lockfile or a Docker image). Keep configs
   and seeds in files, and log the hostname and GPU with every result.
3. **RTX 50-series (Blackwell, sm_120):** use PyTorch wheels built for CUDA 12.8 or newer. Check that
   the bitsandbytes, vLLM, and flash-attn versions you pin have sm_120 support.
4. **WSL2:**
   - Install only the Windows NVIDIA driver. Never install a Linux driver inside WSL.
   - Keep the repo and data on the Linux filesystem (`~/`), not `/mnt/c`.
   - If you run out of RAM, raise the WSL memory limit in `%UserProfile%\.wslconfig`.
5. Confirm 4090 access in Week 1: SSH/remote access, overnight jobs, persistent storage, and
   whether you can install packages without admin rights. If access is limited, run the closed
   LLMs through APIs and keep the encoder work on the 5060.
