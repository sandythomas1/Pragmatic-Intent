# Related work: evidence notes and paper draft

_2026-10-23. First research pass for spec 001 FR-11. This is a short logged search, not a
systematic review. The paper draft below is provisional; no new model results are claimed._

## Positioning decision for the draft

The defensible contribution is an evaluation of **how context benefit varies with rule-assigned
request indirectness in text assistant dialogue**, with separate detection, oracle interpretation
and routed interpretation scores. It combines existing ideas in one controlled study. This search
does not establish a first-of-its-kind claim.

Context ablations, contextual intent inference, graded indirectness and corruption controls all
have precedents. The closest comparisons are DIRECT, DRInQ, READI, INDIR-IT and the earlier ISA
schema work. The differences below describe the reviewed designs; they do not prove that no
other study has used this project's complete design.

The current implementation follows spec 001's option A and D-07, rather than the older labeling
plan: versioned wording rules, MultiWOZ act references, and dialogue-cluster bootstrap contrasts.
Option A retains DIRECT's direct/indirect rewrites in Stage 1; describe their provenance rather
than claiming an original-turn-only evaluation. The older research-plan prose is superseded here.
These references support a study with explicit proxy-label limitations. They do not turn the
rules or corpus acts into independently validated speaker-intent gold.

## Evidence map

“Body” means the listed sections were inspected in the primary paper. “Abstract” means only
the primary abstract and publication metadata were checked in this pass. Reading is incomplete
where marked; the table is not a claim that every paper was read cover to cover.

| Reference and primary source | Evidence checked | What overlaps and what to distinguish |
|---|---|---|
| Takayama, Kajiwara & Arase (2021), [DIRECT: Direct and Indirect Responses in Conversational Text Corpus](https://aclanthology.org/2021.findings-emnlp.170.pdf) | Body: §§3.1–3.3, 4.1–4.3; Tables 6, 8, 10 | Crowd-authored pragmatic rewrites of MultiWOZ turns, with history. History helps indirect-to-direct generation but does not improve every task. Directness prediction already compares BERT with/without history and a lexical model. Our question concerns context benefit across wording-rule levels and structured request recovery. |
| George & Mamidi (2020), [Conversational implicatures in English dialogue: Annotated dataset](https://www.sciencedirect.com/science/article/pii/S1877050920312436) | Abstract; [2019 preprint metadata](https://arxiv.org/abs/1911.10704) cross-checked | Manually annotated context–utterance–implicated-meaning snippets from English tests and movie scripts. Relevant to representation of implied meaning; those annotations do not directly supply assistant request labels. Cite the 2020 published article when using that edition. |
| Mannekote et al. (2025), [Making Task-Oriented Dialogue Datasets More Natural by Synthetically Generating Indirect User Requests](https://aclanthology.org/2025.coling-main.696.pdf) | Body: §§4–5, 6.1, 9–10 | GPT-generated, crowd-rated requests based on SGD slot schemas; the seed set has 453 items. The paper evaluates ambiguity and world-knowledge criteria, including slot-value inference. Our transfer table uses the pinned release separately; it cannot establish a dialogue-context interaction or false-positive rate. |
| Żelasko, Pappagari & Dehak (2021), [What Helps Transformers Recognize Conversational Structure? Importance of Context, Punctuation, and Labels in Dialog Act Recognition](https://aclanthology.org/2021.tacl-1.69/) | Abstract and publication metadata | Broader conversational context helps disambiguate dialogue acts in Switchboard and MRDA. This establishes a context precedent, while its segmentation/act task differs from request interpretation. Follow the TACL volume year, 2021; the journal site also lists a January 2022 posting date. |
| Arai & Ren (2026), [DRInQ: Evaluating Conversational Implicature with Controlled Context Variation](https://aclanthology.org/2026.acl-long.1597/), [body consulted](https://arxiv.org/html/2605.24267v1) | Body: §§3.2–3.7; ACL publication record | Fixed questions receive different contextual framings and five candidate interpretations. Human verification and a challenge subset are explicit. The challenge selection uses annotator/model disagreement (§3.7); this project's selection stays independent of predictions. Different framings can change DRInQ's intended answer; our ablations retain the historical reference. |
| Kim et al. (2026), [READI: Read the Room, Read the Image](https://aclanthology.org/2026.findings-acl.1556.pdf) | Body: §5.1.2, §5.1.3, Table 7; [arXiv Appendix A](https://arxiv.org/html/2608.30270v1#A1) | English/Korean visual pragmatic QA with graded indirectness. The published paper already shuffles images across items as an unrelated-context ablation. Its levels and multimodal setting do not validate our wording rules. Avoid claiming novelty for either indirectness gradients or shuffled-context controls. |
| Orsini & Brunato (2025), [Direct and Indirect Interpretations of Speech Acts: Evidence from Human Judgments and Large Language Models](https://aclanthology.org/2025.clicit-1.79.pdf) (INDIR-IT) | Body: §§2.2, 3.1, human-results discussion | A manually curated Italian benchmark has 40 non-conventionalized scenarios and 30 conventionalized pairs. Each pair holds the utterance fixed in literal-favoring versus indirect-favoring contexts. This is a close contextual speech-act comparison, not merely background about Italian. Our historical-reference ablations and act/slot outputs differ. |
| Roque et al. (2020), [Developing a Corpus of Indirect Speech Act Schemas](https://aclanthology.org/2020.lrec-1.28.pdf) | Body: §§4.5–6; abstract | ISA schemas predate the recent LLM benchmarks. The authors discuss constructing contextual alternatives and scaling corpus-grounded authoring. Their pilot starts from “Can you” utterances in DailyDialog. Credit this lineage; original-source context ablation is a different operation from authoring contexts that license alternative readings. |
| Louis et al. (2020), [“I'd rather just go to bed”: Understanding Indirect Answers](https://aclanthology.org/2020.emnlp-main.601/) (Circa) | Abstract and publication metadata | Crowdsourced polar-question/indirect-answer pairs include uncertain and conditional meanings. Useful evidence that indirect meaning exceeds binary labels. Answer interpretation does not establish whether a turn requests an action. |
| Hu et al. (2023), [A fine-grained comparison of pragmatic language understanding in humans and language models](https://aclanthology.org/2023.acl-long.230/) | Abstract and publication metadata | Expert-curated English materials compare human/model interpretations, error types and linguistic cues across seven phenomena. Motivates separating correct interpretation from superficial answer selection. We cannot claim a human-comparison contribution without independent human measurements. |
| Ma et al. (2025), [Pragmatics in the Era of Large Language Models: A Survey on Datasets, Evaluation, Opportunities and Challenges](https://aclanthology.org/2025.acl-long.425/) | Abstract and publication metadata | Maps pragmatic phenomena, collection methods and evaluation designs. Use as an orientation source; cite individual benchmark papers for their actual methods and results. |
| Li (2022), [Text Classification of Conversational Implicatures Based on Lexical Features](https://www.tandfonline.com/doi/full/10.1080/08839514.2022.2127598) | Body: abstract, experiment procedure and context comparisons | Lexical logistic regression is evaluated with and without context on a 600-item implicature subset. This is an additional classical-model precedent. Its yes/no implicature labels and feature-based classification differ from request detection and supported act/slot recovery. |
| Li et al. (2026), [Keep It InMind: Benchmarking the Implicit-Association Blind Spot in Agent Memory](https://arxiv.org/html/2607.24368v1) | Body: §2.1, §4.3–4.4, limitations | Adjacent work separates memory retrieval failure from the ability to apply visible information. User facts are synthetic. Its in-context control motivates careful attribution of pipeline failure; agent memory retrieval is outside this December study. Include only if space permits. |

## Draft related-work section

### Pragmatic meaning and assistant dialogue

Resources for pragmatic inference represent several different targets. George and Mamidi
annotate implied meanings in contextualized dialogue snippets, while Circa focuses on meanings
of indirect answers to polar questions. These resources support contextual interpretation but
their labels do not automatically identify requests to an assistant.
([George & Mamidi, 2020](https://www.sciencedirect.com/science/article/pii/S1877050920312436);
[Louis et al., 2020](https://aclanthology.org/2020.emnlp-main.601/))

DIRECT is the closest data and task predecessor: it augments MultiWOZ with human-authored
pragmatic paraphrases and evaluates directness and paraphrase generation, including comparisons
with and without dialogue history. Its differing context effects across tasks motivate examining
detection and interpretation separately. Under option A, the present study retains DIRECT's
rewrites and distinguishes rule-assigned wording levels from the source's variant labels.
([Takayama et al., 2021](https://aclanthology.org/2021.findings-emnlp.170.pdf))

IndirectRequests instead constructs requests from SGD schemas using an LLM generation pipeline
and crowd evaluation. It provides a relevant transfer task for slot-value recovery, with a
different source and task design from contextual dialogue evaluation. We report it separately.
([Mannekote et al., 2025](https://aclanthology.org/2025.coling-main.696.pdf))

### Context, indirectness and evaluation design

Context-dependent speech-act interpretation has a substantial experimental lineage, including
ISA schemas and INDIR-IT's paired literal and indirect contexts. DRInQ systematically varies
context around fixed questions, whereas READI examines graded indirectness with visual context
and a shuffled-image control. Consequently, neither contextual inference nor a context corruption
control is a new contribution of this study.
([Roque et al., 2020](https://aclanthology.org/2020.lrec-1.28.pdf);
[Orsini & Brunato, 2025](https://aclanthology.org/2025.clicit-1.79.pdf);
[Arai & Ren, 2026](https://arxiv.org/html/2605.24267v1);
[Kim et al., 2026](https://aclanthology.org/2026.findings-acl.1556.pdf))

Context also helps disambiguate conversational acts beyond request benchmarks. Lexical
classification studies further show why a context-free baseline is informative, rather than
assuming every successful classification requires pragmatic reasoning.
([Żelasko et al., 2021](https://aclanthology.org/2021.tacl-1.69/);
[Li, 2022](https://www.tandfonline.com/doi/full/10.1080/08839514.2022.2127598))

Broader pragmatic evaluations compare human and model interpretations across phenomena, and
recent surveys organize the available resources and evaluation choices. Our narrower question
is whether the benefit of preceding text context varies across rule-assigned indirectness levels
in assistant dialogue, and how detection, oracle interpretation and routed interpretation differ.
The proposed comparison holds target wording and historical act references fixed across context
conditions. It remains limited by proxy labels, observed rather than randomized indirectness,
and the selected model panel.
([Hu et al., 2023](https://aclanthology.org/2023.acl-long.230/);
[Ma et al., 2025](https://aclanthology.org/2025.acl-long.425/))

## Claims to keep out of the paper

- “First context ablation for indirect requests.” DIRECT and contextual speech-act resources
  make that claim untenable on the evidence above.
- “First mismatched-context control.” READI already has shuffled visual context; specify the
  present control's text-dialogue construction instead.
- “Indirectness causes model failure.” Indirectness is observed here; context is manipulated.
- “Validated human intent benchmark.” Option A uses rule levels and corpus act references.
- “Original-turn-only evaluation.” Option A retains human-authored rewrite variants in Stage 1.
- “Independent human agreement” from an LLM review, or “ambiguity measurement” from rule levels.
- “General model-family superiority” from a small selected panel or shared interpretation model.

## Search log

All searches below were run on **2026-10-23** using web search. Search results were discovery
leads; the evidence map relies on primary papers, publisher records or author-maintained sources.
No benchmark items were downloaded or selected for this pass. This is a scoped update through
the search date, with no exhaustive-coverage claim.

| Exact query | Follow-up |
|---|---|
| `"READI" "2608.30270"` | Verified arXiv body and the ACL 2026 Findings paper. |
| `"DRInQ" "2605.24267"` | Verified arXiv body and authors' institution record. |
| `"Mannekote" "IndirectRequests"` | Read the COLING 2025 paper's methods. |
| `George Mamidi 2020 conversational implicatures annotated dataset` | Checked publisher abstract and preprint date. |
| `Żelasko Pappagari Dehak 2021 dialogue acts context transformers` | Checked TACL record and abstract. |
| `"indirect requests" "context" "2026" benchmark` | Found adjacent InMind work; opened its primary paper. |
| `"pragmatics" "context" "indirectness" benchmark 2025 2026` | Found INDIR-IT; opened its primary paper. |
| `"Direct and Indirect Interpretations of Speech Acts" humans language models` | Verified authors, venue and paired-context design. |
| `"InMind" "2607.24368"` | Checked author repository and arXiv methods; kept as adjacent. |
| `"indirectness" "context" "benchmark" site:aclanthology.org/2026` | Located READI's proceedings edition. |
| `"context" "indirect requests" "benchmark" site:aclanthology.org/2025` | Cross-checked IndirectRequests and INDIR-IT. |
| `"DRInQ" site:aclanthology.org` | Verified ACL 2026 publication record. |
| `"Text Classification of Conversational Implicatures Based on Lexical Features"` | Checked publisher methods for a classical-model precedent. |
| `"Developing a Corpus of Indirect Speech Act Schemas"` | Followed INDIR-IT's backward citation to Roque et al. |

Direct opens also checked the proposal's DIRECT reference and the existing Circa, Hu and Ma
links. Venue claims for DRInQ/READI use publisher records; detailed DRInQ notes above refer to
arXiv v1 and should be checked against the proceedings edition before final submission.

## Remaining reading and manuscript work

1. Finish the body-level reading for George & Mamidi, Żelasko, Circa, Hu and Ma; check the
   proceedings version of DRInQ against the cited v1 methods. Update this evidence map if needed.
2. Read the original CCSARP source before making detailed theoretical claims about its scale.
   READI's use of CCSARP does not independently validate this project's rules.
3. Have Sandy review the draft's positioning and decide its final length with the course professor.
   This pass does not close FR-11 or the paper-writing work package.
4. Rerun a short logged literature search before submission. Add result-specific comparisons only
   after frozen test results exist; published scores on different tasks are not a shared leaderboard.
