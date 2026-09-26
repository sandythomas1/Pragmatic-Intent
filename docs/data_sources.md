# Data Sources and Provenance

_Last verified: 2026-09-25. Machine-readable manifest: [`data/sources.toml`](../data/sources.toml)._

This page records where each third-party dataset comes from, the exact version we pinned, its
license, what it contains, and how this project may use it. The raw files are **not** in git:
`data/raw/` is ignored because each source carries its own license. Anyone reproducing the project
downloads the files with the script below. The script checks every file against the SHA-256 pinned
in the manifest.

## Getting the data

Requires Python 3.11 or newer. Uses the standard library only, so no environment setup is needed.
Run from the repository root:

```bash
python -m src.data.download_sources                  # download and verify everything (~420 MB on disk, mostly MultiWOZ data.json)
python -m src.data.download_sources --only circa     # one or more named sources
python -m src.data.download_sources --verify-only    # re-hash local files, no network
python -m src.data.download_sources --list           # show pinned URLs, versions, licenses
python -m src.data.build_direct_dataset              # join DIRECT to MultiWOZ into data/interim/direct/ (see "MultiWOZ 2.1")
python -m unittest discover -s tests -t .            # unit tests (no network, no real data)
```

The downloader is idempotent: a file that exists and matches its checksum is skipped. A size or
checksum mismatch aborts that source and makes the command exit with status 1. It only fetches
`https://` URLs on hosts listed in the manifest, and redirects must stay on those hosts too. From
archives it extracts only the named members, only if they are regular files, and only to paths
inside `data/raw/<name>/`.

**Manual steps:** none. All seven sources are public and download without a login, a license
click-through, or a form.

## Summary

| Source | Pinned version | Local path (`data/raw/…`) | Records | License | Intended use |
|---|---|---|---|---|---|
| DIRECT | git `0326be4` (2021-07-01) | `direct/` | 71,498 pairs (64,126 train / 7,372 test) | **None stated** | **Core data** (existing-data design, 2026-09-25) |
| MultiWOZ 2.1 | git `fe0c8e6`, `MultiWOZ_2.1.zip` | `multiwoz/MultiWOZ_2.1/` | 10,438 dialogues | MIT | Context, Stage 2 labels (domain + user acts), official splits for DIRECT |
| IndirectRequests | HF `9a06e68` (2024-02-02) | `indirect_requests/` | 453 (123 / 136 / 194) | **Ambiguous** (apache-2.0 vs mit; SGD-derived) | Transfer eval (Stage 2 slot), taxonomy reference |
| Circa | git `02ad965` (2020-10-08) | `circa/` | 34,268 QA pairs | **Ambiguous** (CC BY 4.0 text, CC BY-SA 4.0 link) | Transfer eval, `no_request` reference |
| CLINC150 | git `828f809` (2021-06-01) | `clinc150/` | 23,700 (22,500 in-scope + 1,200 OOS) | CC BY 3.0 | Seed utterances, taxonomy reference |
| MASSIVE (en-US) | 1.1 tarball | `massive/1.1/` | 16,521 (11,514 / 2,033 / 2,974) | CC BY 4.0 | Seed utterances, taxonomy reference |
| Conversational Implicatures (George & Mamidi) | Figshare v7 (2023-05-31) | `conv_implicatures/` | 1,000 (context, response, implicature) | **CC BY 4.0 declared, but the text is third-party copyrighted** | Stage 2 annotation reference, `no_request`/implicature examples |

### Licensing and release status: read this before publishing anything

We plan to publish the benchmark on Hugging Face, so the question is what may be **redistributed**,
not only what may be used. Evaluating models on a dataset and reporting the numbers does not
redistribute it. Copying its text into our release does. (This is an engineering reading of the
license texts, not legal advice.)

| Source | May we copy its text into our released benchmark? | Action |
|---|---|---|
| DIRECT | **No.** With no license stated, default copyright applies. | Use it locally for training and evaluation only. If we want to release derived items, email the authors (Takayama / Arase) for permission. Keep every file derived from DIRECT out of git. |
| MultiWOZ 2.1 | Yes, keeping the MIT copyright and permission notice. Any record that combines MultiWOZ context with DIRECT text is still bound by DIRECT's restriction. | Cite Budzianowski et al. (2018) and Eric et al. (2020). |
| IndirectRequests | **Unclear.** The card declares two licenses (apache-2.0 in the parsed header, mit in a second block). Its situations and slot descriptions come from SGD, which is CC BY-SA 4.0. | Don't copy its items. If needed, ask the first author which license applies. |
| Circa | **Unclear.** The README names CC BY 4.0 but links to CC BY-SA 4.0. The HF mirror says cc-by-4.0. | Treat it as CC BY-SA 4.0 (the stricter reading) until clarified (contact: circa@google.com). Copying it would force ShareAlike on the release. |
| CLINC150 | Yes, with attribution (CC BY 3.0). | Record `derived_from` and cite it. |
| MASSIVE | Yes, with attribution (CC BY 4.0, which also covers SLURP). | Record `derived_from` and cite both MASSIVE and SLURP. |
| Conversational Implicatures | **No, not the dialogue text.** Figshare declares CC BY 4.0, but the utterances were transcribed from TOEFL practice tapescripts and IMSDb movie scripts, which the uploader doesn't own and can't relicense. Only the uploader's own implicature annotations are plausibly covered. | Treat it like DIRECT: local use and citation only, and keep derived files out of git. Paraphrasing its *structure* (context → response → implied meaning) is fine. |

---

## DIRECT

- **Canonical source:** <https://github.com/junya-takayama/DIRECT>. The paper links to it in footnote 1.
- **Paper:** Takayama, Kajiwara & Arase. "DIRECT: Direct and Indirect Responses in Conversational
  Text Corpus." *Findings of EMNLP 2021*, pp. 1980–1989. A Japanese journal version appeared in
  *JNLP* 29(1), 2022.
- **License:** none stated. The repository has no LICENSE file (the GitHub API reports `license: null`),
  and neither the README nor the paper contains a license or terms-of-use statement. Checked
  2026-09-25.
- **Version pulled:** commit `0326be46e80aa2627e99aceb88a3e0b9e91dd915` (2021-07-01), which is the only
  published revision.
- **Files:**

  | File | Bytes | SHA-256 |
  |---|---|---|
  | `train.csv` | 13,318,218 | `48b7de2530eae7120a75d769a21d7044fcc2060b9ae3556a988cf34545dc4979` |
  | `test.csv` | 1,634,556 | `68a9b870440dcd818db2c75ea97661ab1c689dd34633426ec579fd427b743722` |
  | `README.md` | 1,791 | `69c9c852f362777e9a43d627f8d97913030a55692bd7a992633cbcac84223c36` |

- **Format:** UTF-8 CSV with a leading unnamed index column (a pandas artifact).
- **Records:** train has 64,126 rows over 9,438 dialogues. Test has 7,372 rows over 1,000 dialogues.
  The total of 71,498 matches the paper. The dialogue counts fit MultiWOZ train+val / test.
- **Fields:** `dialogue_id` (a MultiWOZ file name such as `MUL1182.json`), `turn_index` (0-based and
  always even, so only user turns appear), `target_utterance` (the original MultiWOZ user turn),
  `direct_utterance`, `indirect_utterance`. `test.csv` adds `isacceptable_direct` / `isacceptable_indirect`
  (True/False) and `quality` (Good/Neutral/Bad).
- **Quality signal (test):** 369 of 7,372 indirect paraphrases (5.0%) were judged *not* to keep the
  original intent. `quality` is Good 6,004 / Neutral 588 / Bad 780.
- **What it gives us:** human-written paraphrases from MTurk in 2021, before LLM text was common, so
  it is a non-LLM source for decision #7. It pairs direct and indirect versions of the same
  intent, with a real multi-turn history through MultiWOZ. The `indirect → direct` pairs are good
  supervision for Stage 2 free-text paraphrase. It is also the only downloaded source with
  multi-turn context.
- **What it can't give us:**
  - No L0–L3 ladder. "Indirect" is not controlled by CCSARP level: about 15% of indirect paraphrases
    still use "can/could/would you", which is L1 form.
  - No `no_request` label. By MultiWOZ user dialogue acts, 16.3% of targets (11,681) are only
    thanks, bye, or greeting, so both paraphrases are non-requests. A cruder regex estimate was 21%.
    Another 10.3% have no user acts at all.
  - No contrastive twins.
  - Its domains are MultiWOZ services (restaurant, hotel, attraction, train, taxi, hospital, police),
    not assistant intents.
- **Caveats:**
  - Dialogue history is **not** in the files. It is joined from MultiWOZ **2.1** on
    `dialogue_id`/`turn_index`: all 71,498 rows match (see [MultiWOZ 2.1](#multiwoz-21)).
  - Some crowd paraphrases are wrong. For example, a "direct" paraphrase turns "moderately priced" into "cheap".

### Novelty check: what DIRECT already did (checked 2026-09-25)

This is the key prior-work risk for the existing-data design. Quotes are from the Findings paper.

- **Tasks:** "an indirect-to-direct transfer task (Section 4.1), direct-to-indirect transfer task
  (Section 4.2), and directness prediction task (Section 4.3)".
- **Models and metrics:**
  - The two transfer tasks use `facebook/bart-base` with and without history, plus a Transformer
    trained from scratch with history. They report **BLEU and perplexity**.
  - Directness prediction uses `bert-base-cased` with and without history, pointwise and pairwise,
    plus a bag-of-words linear regression without history. It reports **exact match and Kendall's
    tau**, with gold scores of 1.0 / 0.5 / 0 for the direct / original / indirect versions.
- **History was binary only (full vs. none):**
  - "We also constructed a model that disregards dialogue history (BART without history) to
    investigate the effects of context."
  - The history is every prior turn: "These utterances are concatenated in the order of appearance
    in the dialogue history". No truncation, last-k variation, or mismatched control is reported.
- **What history did:**

  | Task | Without history | With history | Paper's verdict |
  |---|---|---|---|
  | Indirect→direct (BART BLEU) | 32.51 | 33.77 | modest gain |
  | Direct→indirect (BART BLEU) | 27.12 | 26.52 | "dialogue history did not improve the BLEU score and perplexity" |
  | Directness prediction (BERT pairwise exact match) | 0.816 | 0.813 | "The BERT models disregarding dialogue history achieved higher scores than the models that use dialogue history" |

- **By degree of indirectness:** no per-level breakdown. Indirectness is only DIRECT's relative
  ordering of paraphrases (direct > original > indirect). The one directness-conditioned result
  splits the *original* MultiWOZ test turns by the best ranking model's prediction: "The model
  predicted 1,842 responses as indirect and 5,530 responses as direct". It then reports the UBAR
  system-response BLEU for each group ("10.25 and 14.09, respectively"). That is one system and one
  binary, predicted split, with no context manipulation.

**How we differ from DIRECT.**
- **Graded, controlled context.** We use none, the one preceding system turn, and the full history,
  plus a length-matched *mismatched* history from a same-split dialogue with no shared domain.
  DIRECT only contrasted full history with none, so it cannot separate "relevant context helps" from
  "more tokens help".
- **Independent indirectness labels.** A human labels CCSARP levels (L0–L3) from the utterance alone.
  DIRECT only ranks its paraphrases relative to each other. With our labels we can test the context
  × indirectness interaction (does context help *more* as utterances get less direct?), which DIRECT
  never examined.
- **Classification, not generation.** We evaluate Stage 1 detection and Stage 2 intent (from MultiWOZ
  domain + user acts) across model families (TF-IDF, fine-tuned encoders, LLMs) with a mixed-effects
  test, rather than generation or ranking.
- **Caveat:** Stage 1 (direct vs. indirect) on DIRECT's own paraphrase pairs is close to DIRECT's
  directness-prediction task, where BERT reached 0.816 pairwise exact match without history. On its
  own it is a replication. The contribution rests on the context × level interaction and the
  mismatched control.

**How we differ from follow-ups.**
- **Closest follow-up:** the authors' own journal version (Takayama, Kajiwara & Arase, *JNLP* 29(1),
  2022).
  - It repeats the three benchmarks with the same binary history ablation (identical tables).
  - It adds one end-to-end experiment that feeds DIRECT's direct paraphrases to UBAR (COMBINED
    99.27 → 100.34 with generated paraphrases, 100.82 with reference paraphrases).
  - It still doesn't vary history length, use a mismatched control, or break results down by
    indirectness level.
- **Other citing papers:** none of the 12 that Semantic Scholar lists (2026-09-25) runs a context ×
  indirectness analysis on DIRECT.
  - I checked full text for INLI (implied NLI), IDIC-DST, and the pragmatic-theory prompting paper.
    They use other data (Circa, LUDWIG, MultiWOZ DST, PragMega) or cite DIRECT only as related work.
  - The others study different phenomena: indirect answers to wh-questions and yes/no questions,
    indirect entity references, visual ambiguity (VAGUE), private thoughts (HOTATE), N-best decoding,
    and a paywalled IJMLC paper on implicature classification that I checked by abstract only.
- **Not yet checked:** I did not query Google Scholar programmatically. Check its "Cited by" list
  manually before submission.

```bibtex
@inproceedings{takayama-etal-2021-direct-direct,
    title = "{DIRECT}: Direct and Indirect Responses in Conversational Text Corpus",
    author = "Takayama, Junya and Kajiwara, Tomoyuki and Arase, Yuki",
    booktitle = "Findings of the Association for Computational Linguistics: EMNLP 2021",
    month = nov,
    year = "2021",
    address = "Punta Cana, Dominican Republic",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2021.findings-emnlp.170/",
    doi = "10.18653/v1/2021.findings-emnlp.170",
    pages = "1980--1989"
}
```

## MultiWOZ 2.1

- **Canonical source:** <https://github.com/budzianowski/multiwoz>, file `data/MultiWOZ_2.1.zip`,
  pinned to commit `fe0c8e65cfcd8462bd33c86e35f21addc84ca82b` (2025-01-14).
- **Papers:** Budzianowski et al., *EMNLP 2018* (MultiWOZ). Eric et al., *LREC 2020*, pp. 422–428
  (version 2.1).
- **License:** MIT. From the repository's
  [LICENSE](https://github.com/budzianowski/multiwoz/blob/fe0c8e65cfcd8462bd33c86e35f21addc84ca82b/LICENSE):
  > "The MIT License (MIT) / Copyright (c) 2019 Paweł Budzianowski / Permission is hereby granted,
  > free of charge, to any person obtaining a copy of this software and associated documentation
  > files (the "Software"), to deal in the Software without restriction …"

  The README inside the zip adds "Copyright Cambridge Dialogue Systems Group, 2018".
- **Files:** the downloader fetches the zip, extracts four members, and deletes the zip. It fetches
  `LICENSE` separately.

  | File | Bytes | SHA-256 |
  |---|---|---|
  | `MultiWOZ_2.1.zip` (deleted after extraction) | 20,241,542 | `8db3f6afe591383b8523b271f07727693e73012ecce47f3ac7987191e09b7523` |
  | `MultiWOZ_2.1/data.json` | 374,423,663 | `8be37ba1cb5b5a35943f32d4dbe03c5017dd88e15716f74987f60e0ece37851c` |
  | `MultiWOZ_2.1/valListFile.txt` | 13,507 | `8e19240b90576c3ed83a0d44ef5e7ca8916e47356662ed4621e6b39d8c327d80` |
  | `MultiWOZ_2.1/testListFile.txt` | 13,497 | `56fff5bf8c7b0a64fba8672241a7bdd947c3a58986bf06f46d37f33288f73ce0` |
  | `MultiWOZ_2.1/README` | 3,118 | `6db60b1b22b9d7d0c16c46fa009e880259564712c057e03b43409c1851f3e07b` |
  | `LICENSE` | 1,086 | `d84d5c0261e1cfc4b4f10f16497feb217800ae6bf89240ee5622a75f659f5124` |

  Not extracted: `system_acts.json` (the user acts are already inline in `data.json`), the database
  files, and the ontology.
- **Which version DIRECT uses (checked empirically, 2026-09-25).** The DIRECT paper says it "employed
  MultiWoZ 2.1". For all 71,498 DIRECT rows, `target_utterance` was compared with each version's turn
  text at `turn_index`. Normalized means whitespace collapsed and lowercased.

  | Version | Source | Exact match | Normalized match | Dialogues missing |
  |---|---|---|---|---|
  | 2.0 | same repo, `MultiWOZ_2.0.zip` | 88.54% | 99.957% (31 misses) | 0 |
  | **2.1** | `MultiWOZ_2.1.zip` | 88.58% | **100.000%** | 0 |
  | 2.2 | same repo, `MultiWOZ_2.2/` | 87.29% | 99.936% | 2 |
  | 2.4 | `smartyfh/MultiWOZ2.4` @ `6807c1d` | 88.58% | 100.000% | 0 |

  - **Every exact-match failure in 2.1 is outer whitespace only** (8,163 rows).
  - **2.4 has the same text** as 2.1 but no user dialogue acts in `data.json`, so **2.1** was chosen.
- **What `turn_index` counts:** it is a 0-based index into the full turn list (user *and* system
  turns). DIRECT has only even values, which are user turns. Reading it as a user-turn counter matches
  only 14.6% of rows, which is mostly turn 0 by coincidence.
- **Splits:**
  - DIRECT `test.csv` covers exactly MultiWOZ's `testListFile` (1,000 dialogues).
  - DIRECT `train.csv` covers MultiWOZ train (8,438) plus val (1,000). No dialogue appears in both
    DIRECT train and test.
  - Our dev split is DIRECT-train rows whose dialogue is in MultiWOZ's `valListFile`, so it is grouped
    by dialogue. (The DIRECT authors used a random, unreleased 2,000-dialogue validation sample instead.)
- **Dialogue acts:**
  - Every turn in `data.json` has an inline `dialog_act`. User turns carry 17 act types:
    `<Domain>-Inform` and `<Domain>-Request` for 7 domains, plus `general-thank`, `general-bye`, and
    `general-greet`.
  - 7,333 DIRECT targets (10.3%) have an empty act dict.
  - System turns also carry the cumulative belief state (`metadata`).
- **What it gives us:** the dialogue history for every DIRECT row, Stage 2 intent labels (domain +
  user act), and official, dialogue-grouped splits.
- **What it can't give us:** anything outside booking and information services. Its user acts are also
  coarse (Inform/Request per domain), so they are not a request-type taxonomy.

**Built dataset** (`python -m src.data.build_direct_dataset`, seed 20260925, written to the
git-ignored `data/interim/direct/`):
- `dialogues.jsonl` holds each dialogue once. `items.jsonl` holds one record per DIRECT row.
- The context conditions (`none`, `one`, `full`, `mismatched`, `mismatched_one`) are derived at load
  time by `src.data.direct_dataset.build_context`.
- All 71,498 rows join. Splits are train 56,755 / dev 7,371 / test 7,372 rows (8,438 / 1,000 / 1,000
  dialogues).
- 172 rows (0.24%) have no valid mismatch donor. All of them are long, multi-domain turns (t ≥ 12).
- Full statistics are in `build_info.json`.

```bibtex
@inproceedings{budzianowski-etal-2018-multiwoz,
    title = "{M}ulti{WOZ} - A Large-Scale Multi-Domain {W}izard-of-{O}z Dataset for Task-Oriented Dialogue Modelling",
    author = "Budzianowski, Pawe{\l} and Wen, Tsung-Hsien and Tseng, Bo-Hsiang and Casanueva, I{\~n}igo and Ultes, Stefan and Ramadan, Osman and Ga{\v{s}}i{\'c}, Milica",
    booktitle = "Proceedings of the 2018 Conference on Empirical Methods in Natural Language Processing",
    year = "2018",
    address = "Brussels, Belgium",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/D18-1547/",
    doi = "10.18653/v1/D18-1547",
    pages = "5016--5026"
}

@inproceedings{eric-etal-2020-multiwoz,
    title = "{M}ulti{WOZ} 2.1: A Consolidated Multi-Domain Dialogue Dataset with State Corrections and State Tracking Baselines",
    author = "Eric, Mihail and Goel, Rahul and Paul, Shachi and Sethi, Abhishek and Agarwal, Sanchit and Gao, Shuyang and Kumar, Adarsh and Goyal, Anuj and Ku, Peter and Hakkani-Tur, Dilek",
    booktitle = "Proceedings of the Twelfth Language Resources and Evaluation Conference",
    month = may,
    year = "2020",
    address = "Marseille, France",
    publisher = "European Language Resources Association",
    url = "https://aclanthology.org/2020.lrec-1.53/",
    pages = "422--428"
}
```

## IndirectRequests

- **Canonical source:** <https://huggingface.co/datasets/msamogh/indirect-requests>, the first author's
  HF account. The COLING paper links to it in footnote 1. The author's older
  `msamogh/sgd-indirect-utterances` repo (291 undocumented instruction-tuning rows) is a precursor
  and is not used.
- **Paper:** Mannekote, Nam, Li, Boyer & Dorr. "Making Task-Oriented Dialogue Datasets More Natural by
  Synthetically Generating Indirect User Requests." *COLING 2025*, pp. 10449–10459. Cite this
  version, not arXiv:2406.07794.
- **License (ambiguous):** the dataset card
  ([README at the pinned revision](https://huggingface.co/datasets/msamogh/indirect-requests/blob/9a06e685c89286eb2bb8026411d150532f86ccb3/README.md))
  opens with the YAML header `license: apache-2.0`, which is what HF displays. Later the same file
  embeds a second YAML block with `license: mit`. The paper states no data license. The items are
  built from SGD schemas ("using the schemas from the SGD dataset"), and SGD is
  [CC BY-SA 4.0](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue#license).
- **Version pulled:** HF commit `9a06e685c89286eb2bb8026411d150532f86ccb3` (2024-02-02).
- **Files:** HF exposes two configs, `target_slot_value` and `mean_world_understanding`, but their
  files are byte-identical (same git blob IDs and the same SHA-256). We fetch one copy and rename it:

  | Local file | Upstream file | Bytes | SHA-256 |
  |---|---|---|---|
  | `train.jsonl` | `train_target_slot_value.jsonl` | 65,999 | `eabdcc1e5729312f8c51b7d658ce74b5e639c725f828b62027eb735aac8a062e` |
  | `validation.jsonl` | `validation_target_slot_value.jsonl` | 69,756 | `56802a5242b271592ed2ba97c5d0eda9fee023d88301ee1ad4d9c44eb5d9908d` |
  | `test.jsonl` | `test_target_slot_value.jsonl` | 113,480 | `62fd6fd6fe8a9c78bde86cf0d8ea419c0a487ef8858155f6f3d54edc25a97e17` |
  | `README.md` | `README.md` | 1,450 | `9e64d23d5e33f1a6d6fdfd483624298320dd00043e1c4a48a134c87461b3dff0` |

- **Format:** JSON Lines.
- **Records:** 123 / 136 / 194, for 453 in total. This matches paper Table 2. The splits are
  **service-disjoint**: train covers Restaurants_1, Services_3, Media_1, Banks_1, …, and test covers
  Travel_1, Restaurants_2, Movies_1, …. There are 30 SGD services across 14 domains and 37 situations.
- **Fields:**
  - `utterance`, `situation`, `service`, `slot_description`.
  - `possible_slot_values` and `bool_rephrased_slot_values`: a **Python-literal list stored as a
    string**. Parse it with `ast.literal_eval`, never `eval`.
  - `target_slot_value`: one of the possible values, or `"<ambiguous>"` (81 of 453).
  - `mean_world_understanding`: a crowd rating from 1 to 10 (median 5).
  - `creation_date`: every item was generated on 2023-07-26.
- **Generation:** the paper says items were generated with "GPT-3.5 and GPT-4 models from OpenAI" at
  "default settings", with no dated snapshot. They were then filtered and labeled on MTurk.
- **What it gives us:** natural-sounding strong hints (mostly L2) with a gold slot value and a
  closed candidate set. That is a clean transfer test for the Stage 2 "key slot" metric. Its
  five indirection strategies (paper Table 4) are a useful reference for the L2/L3 rubric.
- **What it can't give us:**
  - It is tiny.
  - Every item is a request, so there are no `no_request` items or contrastive twins.
  - The indirectness is about *which slot value* is meant, not *whether* the user is making a request.
  - The release has no dialogue history.
  - There is no level annotation.
  - 6 items contain the target value verbatim.
- **Caveat for decision #7:** the text is **GPT-generated**. Report GPT-family models on this set
  separately, and don't use it as the only transfer test.

```bibtex
@inproceedings{mannekote-etal-2025-making,
    title = "Making Task-Oriented Dialogue Datasets More Natural by Synthetically Generating Indirect User Requests",
    author = "Mannekote, Amogh and Nam, Jinseok and Li, Ziming and Boyer, Kristy Elizabeth and Dorr, Bonnie J.",
    booktitle = "Proceedings of the 31st International Conference on Computational Linguistics",
    month = jan,
    year = "2025",
    address = "Abu Dhabi, UAE",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2025.coling-main.696/",
    pages = "10449--10459"
}
```

## Circa

- **Canonical source:** <https://github.com/google-research-datasets/circa>. There is also an HF
  mirror at `google-research-datasets/circa`, stored as parquet with `cc-by-4.0` metadata. We use the
  GitHub TSV.
- **Paper:** Louis, Roth & Radlinski. "'I'd rather just go to bed': Understanding Indirect Answers."
  *EMNLP 2020*, pp. 7411–7425.
- **License (ambiguous):** from the [README](https://github.com/google-research-datasets/circa/blob/02ad965518ab2fbd8bb24463d312ebb03bac5368/README.md#license):
  > "This dataset is the work of Annie Louis, Dan Roth, and Filip Radlinski from Google LLC, made
  > available under the Creative Commons Attribution 4.0 License. A full copy of the license can be
  > found at https://creativecommons.org/licenses/by-sa/4.0/"

  The text says CC BY 4.0, but the link points to CC **BY-SA** 4.0.
- **Version pulled:** commit `02ad965518ab2fbd8bb24463d312ebb03bac5368` (2020-10-08). The README
  changelog says "2020-10-06: EMNLP 2020 release version".
- **Files:**

  | File | Bytes | SHA-256 |
  |---|---|---|
  | `circa-data.tsv` | 7,766,077 | `98454df6b716dd7ff5f83a3db298849f05414688e81c2ee21b8e5a548ed897aa` |
  | `README.md` | 6,896 | `4444458e63f49968ce5a17b6c86ec5fca53f1c49960c5a99525d8365ff2769f5` |

- **Format:** TSV with 8 columns: `id`, `context`, `question-X`, `canquestion-X`, `answer-Y`, `judgements`,
  `goldstandard1`, `goldstandard2`.
- **Records:** 34,268 QA pairs, 3,345 unique questions, and 10 social situations with roughly
  3,200–3,500 pairs each. There are no official splits.
- **Labels:**
  - `goldstandard1` (strict majority): Yes 14,504 · No 10,829 · NA 2,743 · Yes-subject-to-conditions 2,583 ·
    Probably yes 1,244 · Probably no 1,160 · In the middle 638 · Other 504 · Not sure 63.
  - `goldstandard2` (relaxed): Yes 16,628 · No 12,833 · conditional 2,583 · middle 949 · NA 771 · Other 504.
- **What it gives us:** human-written indirect *answers* with one prior turn (the question) as
  context. It gives a pragmatic-inference transfer test in the "1 prior turn" format. It is also a
  good reference for hint-shaped statements that are **not** requests ("I put hot sauce on
  everything"), which is what our `no_request` distractors need to look like.
- **What it can't give us:** requests of any kind, assistant intents, levels, or multi-turn history.
  Its label space (yes/no polarity) doesn't map onto Stage 1 or Stage 2.

```bibtex
@inproceedings{louis-etal-2020-id,
    title = "``{I}{'}d rather just go to bed'': Understanding Indirect Answers",
    author = "Louis, Annie and Roth, Dan and Radlinski, Filip",
    booktitle = "Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing (EMNLP)",
    month = nov,
    year = "2020",
    address = "Online",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2020.emnlp-main.601/",
    doi = "10.18653/v1/2020.emnlp-main.601",
    pages = "7411--7425"
}
```

## CLINC150

- **Canonical source:** <https://github.com/clinc/oos-eval>. There is also an HF mirror at
  `clinc/clinc_oos` (parquet, `cc-by-3.0`).
- **Paper:** Larson et al. "An Evaluation Dataset for Intent Classification and Out-of-Scope
  Prediction." *EMNLP-IJCNLP 2019*, pp. 1311–1316.
- **License:** CC BY 3.0 Unported. The repository
  [LICENSE](https://github.com/clinc/oos-eval/blob/828f8093932c8fe6ca7936c3d2e52903b1c523de/LICENSE)
  opens with "Creative Commons Legal Code / Attribution 3.0 Unported".
- **Version pulled:** commit `828f8093932c8fe6ca7936c3d2e52903b1c523de` (2021-06-01), file
  `data/data_full.json`. This is the "Full" configuration, the one the README recommends.
- **Files:**

  | File | Bytes | SHA-256 |
  |---|---|---|
  | `data_full.json` | 2,495,390 | `36923c3705a59e08fe9c3883d8bc2dd966ef93e22cb78ac41171782a698d56e0` |
  | `LICENSE` | 19,467 | `e6bc9e9c474700b708f568bac9e5a8a9bcb2b1dad53442f5ba449fcb848b8e76` |
  | `README.md` | 2,668 | `8a8df26c4de3d25b6c4cff385ca23602c30e4e56828b015206cbc202f6db363a` |

- **Format:** a JSON object mapping each split to a list of `[utterance, intent]` pairs.
- **Records:** train 15,000 · val 3,000 · test 4,500 (in-scope) · oos_train 100 · oos_val 100 ·
  oos_test 1,000, for 23,700 in total.
- **Labels:** 150 intents in 10 domains of 15 each: banking, credit_cards, kitchen_and_dining, home,
  auto_and_commute, travel, utility, work, small_talk, meta. The in-scope data has 100/20/30
  utterances per intent across train/val/test. There is also an `oos` (out-of-scope) class.
- **What it gives us:**
  - Direct (L0) and conventionally indirect (L1) seed phrasings for assistant intents, such as
    `smart_home`, `reminder`, `timer`, `restaurant_suggestion`, `text`, `make_call`, and `definition`.
  - Grounding for the taxonomy.
  - Small-talk intents (`greeting`, `goodbye`, `thank_you`, `yes`, `no`, `maybe`, …) that are natural
    `no_request` candidates.
- **What it can't give us:** hints or context. A crude regex finds only 4 of 22,500 in-scope
  utterances that look like hints. Also, **`oos` is not `no_request`**: out-of-scope queries are
  still requests, just outside CLINC's label set.
- **Caveat:** the text is 100% lowercase and 0.4% of utterances end in punctuation. If seeds are used
  verbatim next to generated text, casing and punctuation become a level cue. Normalize both sides,
  or paraphrase the seeds.

```bibtex
@inproceedings{larson-etal-2019-evaluation,
    title = "An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction",
    author = "Larson, Stefan and Mahendran, Anish and Peper, Joseph J. and Clarke, Christopher and Lee, Andrew and Hill, Parker and Kummerfeld, Jonathan K. and Leach, Kevin and Laurenzano, Michael A. and Tang, Lingjia and Mars, Jason",
    booktitle = "Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing and the 9th International Joint Conference on Natural Language Processing (EMNLP-IJCNLP)",
    month = nov,
    year = "2019",
    address = "Hong Kong, China",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/D19-1131/",
    doi = "10.18653/v1/D19-1131",
    pages = "1311--1316"
}
```

## MASSIVE (en-US only)

- **Canonical source:** <https://github.com/alexa/massive>. Its README points to the release tarballs
  on Amazon's S3 bucket (`amazon-massive-nlu-dataset.s3.amazonaws.com`). The HF repo
  `AmazonScience/massive` ships only a Python loading script, which would mean running remote code,
  so we don't use it.
- **Paper:** FitzGerald et al. "MASSIVE: A 1M-Example Multilingual Natural Language Understanding
  Dataset with 51 Typologically-Diverse Languages." *ACL 2023*, pp. 4277–4302 (arXiv 2022). The
  authors ask that SLURP (Bastianelli et al., *EMNLP 2020*) also be cited, because MASSIVE's en-US
  data comes from SLURP.
- **License:** CC BY 4.0. From the repository's
  [NOTICE.md](https://github.com/alexa/massive/blob/f966f21846043aabef9b0f974fa7970027f43738/NOTICE.md):
  > "The MASSIVE dataset is licensed under CC BY 4.0, Copyright Amazon.com Inc. or its affiliates."

  The `LICENSE` file inside the tarball is "Attribution 4.0 International". SLURP text is also
  CC BY 4.0, per the tarball's `NOTICE.md`. The repository *code* is Apache-2.0, but we use none of it.
- **Version pulled:** the MASSIVE 1.1 tarball (S3 Last-Modified 2022-11-07). Per the README, 1.1
  only adds Catalan, so en-US is identical to 1.0.
- **Files:** the downloader fetches the 40 MB archive (52 locales), extracts four members, and
  **deletes the archive**. Only en-US is kept.

  | File | Bytes | SHA-256 |
  |---|---|---|
  | `amazon-massive-dataset-1.1.tar.gz` (deleted after extraction) | 40,251,390 | `4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577` |
  | `1.1/data/en-US.jsonl` | 3,904,197 | `c70f75c6a543a26e249ec383df67733ad9b1066f6c0406c2e04a3f03356e407e` |
  | `1.1/LICENSE` | 18,704 | `c2e6ea015269147de02117ebdd91f30ef09831251f5345fa8365273b1db1d435` |
  | `1.1/NOTICE.md` | 502 | `b90534ccd20c6f0e1e5239567af0d150496339542b75a15bfbc3e1e737593ddb` |
  | `1.1/CITATION.md` | 1,128 | `96d21569b0e2f3b64e7e8a2ff22a5b15570ec3f7f93ffdc26efb01d366fe073f` |

- **Format:** JSON Lines. Fields are `id` (the SLURP id), `locale`, `partition` (train/dev/test),
  `scenario`, `intent`, `utt`, `annot_utt` (slots as `[slot : value]`), and `worker_id`. en-US records
  have no `judgments` field.
- **Records:** 16,521 in total: train 11,514, dev 2,033, test 2,974. There are 18 scenarios and 60 intents:
  alarm, audio, calendar, cooking, datetime, email, general, iot, lists, music, news, play, qa,
  recommendation, social, takeaway, transport, weather.
- **What it gives us:**
  - Slot-annotated L0/L1 voice-assistant commands.
  - The best seed pool for `device_control` (`iot_*`, `audio_volume_*`), scheduling, messaging, and
    recommendations.
  - A small set of **natural L2 hints**: about 30 utterances by a crude regex, for example "it's too
    dark here" → `iot_hue_lighton` and "its too bright in here" → `iot_hue_lightdim`. These are
    useful as human-written exemplars.
- **What it can't give us:** context of any kind, `no_request` labels beyond `general_quirky` /
  `general_greet`, or LLM-assistant intents such as writing help or coaching.
- **Caveat:** the text is lowercase and ASR-normalized, with 0% uppercase and 2.1% ending in
  punctuation. The same casing-artifact warning as CLINC150 applies.

```bibtex
@inproceedings{fitzgerald-etal-2023-massive,
    title = "{MASSIVE}: A 1{M}-Example Multilingual Natural Language Understanding Dataset with 51 Typologically-Diverse Languages",
    author = "FitzGerald, Jack and Hench, Christopher and Peris, Charith and Mackie, Scott and Rottmann, Kay and Sanchez, Ana and Nash, Aaron and Urbach, Liam and Kakarala, Vishesh and Singh, Richa and Ranganath, Swetha and Crist, Laurie and Britan, Misha and Leeuwis, Wouter and Tur, Gokhan and Natarajan, Prem",
    booktitle = "Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)",
    month = jul,
    year = "2023",
    address = "Toronto, Canada",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2023.acl-long.235/",
    doi = "10.18653/v1/2023.acl-long.235",
    pages = "4277--4302"
}

@inproceedings{bastianelli-etal-2020-slurp,
    title = "{SLURP}: A Spoken Language Understanding Resource Package",
    author = "Bastianelli, Emanuele and Vanzo, Andrea and Swietojanski, Pawel and Rieser, Verena",
    booktitle = "Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing (EMNLP)",
    month = nov,
    year = "2020",
    address = "Online",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2020.emnlp-main.588/",
    doi = "10.18653/v1/2020.emnlp-main.588",
    pages = "7252--7262"
}
```

## Conversational Implicatures in English Dialogue (George & Mamidi)

- **Canonical source:** Figshare, "Implicature dataset" by Elizabeth Jasmi George,
  <https://doi.org/10.6084/m9.figshare.10315505>. The paper cites this DOI as reference [32].
  `UCL-DARK/ludwig` on HF is a later derivative (LUDWIG), not the original release.
- **Paper:** George & Mamidi. "Conversational implicatures in English dialogue: Annotated dataset."
  *Procedia Computer Science* 171:2316–2323 (2020). DOI `10.1016/j.procs.2020.04.251`, also
  arXiv:1911.10704. The *article* is CC BY-NC-ND 4.0 per Crossref; that license covers the paper,
  not the data.
- **License:** Figshare metadata declares
  "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)"
  ([landing page, v7](https://figshare.com/articles/dataset/Implicature_dataset/10315505/7)).
  **Caveat:** the paper says the utterances were collected "by transcribing from listening
  comprehension sections of English tests like TOEFL … as well as scraping dialogues from movie
  scripts available on IMSDb". It adds that TOEFL narratives were "manually transcribed from the
  English Test Store website". That text belongs to its original rights holders (the test publishers
  and the film studios), so the uploader can't license it under CC BY. **Don't redistribute the
  dialogue text** (see the licensing table above).
- **Version pulled:** Figshare **v7** (DOI `…10315505.v7`, modified 2023-05-31). The paper cites
  v3, which contained only a PDF ("Implicating dialogues.pdf"). v7 is the first version with the full
  CSV. Figshare file IDs are immutable, so the URLs below are pinned.
- **Files:**

  | Local file | Figshare file (id) | Bytes | SHA-256 |
  |---|---|---|---|
  | `implicature_1-1001.csv` | "Conversational Implicature Dataset 1-1001 - implicature data 1-1001.csv" (24402071) | 96,822 | `3de2fee93c0135185f6b4934e159099124a4c22a6699e2daa17a86cf4e473320` |
  | `Readme.pdf` | "Readme.pdf" (24402074) | 60,914 | `bf397cf8ad69a21a8ac2e4f24e247754ff996121cd9b9aa58ab444fad7602d08` |

  Figshare's published MD5s match both files. Not fetched: the `.xlsx` copy (id 24402077; same
  1,000 rows) and three superseded partial PDFs from earlier versions. Downloads redirect from
  `ndownloader.figshare.com` to Figshare's S3 bucket on `s3-eu-west-1.amazonaws.com`; both hosts are
  in `allowed_hosts`.
- **Format:** UTF-8 CSV with 3 columns: `Context utterance`, `Response utterance`, `Implicature`.
  49 fields contain embedded newlines, and many have trailing whitespace, so use a real CSV parser
  and strip fields.
- **Records:** 1,000. The Figshare description says "1001 utterances", but "1-1001" is the
  spreadsheet row range including the header; the xlsx confirms 1,000 data rows. There are 6
  duplicate (context, response) pairs. The paper says about 500 items come from 74 TOEFL practice
  conversations and about 500 from 45 animated-movie scripts on IMSDb, plus some idiom, metaphor,
  and hyperbole examples.
- **Label structure:** the implicature is free text, with one per row and no annotator IDs or
  agreement statistics. 71.7% of implicatures begin with "Yes" or "No", because 83% of contexts are
  questions, most of them polar. The rest are short paraphrases (mean 3.1 words), such as
  "I already sent my passport application". Only about 2.8% of responses contain request markers
  (crude regex).
- **What it gives us:**
  - **Stage 2 annotation-structure reference.** Its context → literal response → implicated meaning
    format is the shape of our `utterance` + context → `gold_request`.
  - **`no_request` / implicature examples.** These are human-written indirect *answers* that are not
    requests, from sources more varied than Circa (film dialogue, test conversations, idioms). They
    are a style reference for form-matched `no_request` distractors (plan Q8).
  - **A small "1 prior turn" transfer probe.** Use it locally only.
- **What it can't give us:** requests (almost none), assistant intents, L0–L3 levels, multi-turn
  history (one context turn only), or 3-way labels. Its implicatures are mostly yes/no polarity,
  which overlaps with Circa's task rather than ours.

```bibtex
@article{george-mamidi-2020-conversational,
    title = "Conversational implicatures in {E}nglish dialogue: Annotated dataset",
    author = "George, Elizabeth Jasmi and Mamidi, Radhika",
    journal = "Procedia Computer Science",
    volume = "171",
    pages = "2316--2323",
    year = "2020",
    doi = "10.1016/j.procs.2020.04.251"
}

@misc{george-2019-implicature-dataset,
    title = "Implicature dataset",
    author = "George, Elizabeth Jasmi",
    year = "2019",
    publisher = "figshare",
    note = "Version 7",
    doi = "10.6084/m9.figshare.10315505.v7"
}
```

---

## Considered / optional (not downloaded)

The release status and licenses below were checked on 2026-09-25. "No license" means the repository
has no LICENSE file and its README states no license.

| Dataset | Link | Data release / license | Recommendation |
|---|---|---|---|
| **DRInQ** (Arai & Ren, ACL 2026; arXiv:2605.24267) | <https://github.com/hjarai/drinq> (`drinq_validated.csv`, 104 KB / 1,156 CSV lines; commit `96a5eae`) | Released; **no license** | **Skip as data, keep as related work.** It covers questions and implicature, not requests, and without a license we can't redistribute it. At most, use it locally as a small transfer probe for "same surface form, different context". |
| **Is the Pope Catholic?** (Yerukola et al., ACL 2024 short; arXiv:2405.08760) | <https://github.com/Akhila-Yerukola/generative-intention-resolution> (`data/hu_gpt4augmented_turn2_data.csv`) | CC BY 4.0 (README). The underlying items come from Hu et al. (ACL 2023, `jennhu/lm-pragmatics`, which has no license file), and the dialogue chains are GPT-4-generated. | **Skip for now.** It is relevant to how we evaluate Stage 2 (the LLM-judge protocol), not as data. It is also GPT-generated (decision #7). |
| **Korean ISA** (Koo et al., arXiv:2502.10995) | Paper says "publicly available on our GitHub repository at https://github.com/annonymous/" (placeholder) | Not actually released; Korean | **Skip.** It is Korean and not released. Its 40-pair design (same utterance, direct vs. indirect speech act by context) does confirm our contrastive design. |
| **Hota & Jokinen** (arXiv:2510.25426) | none found | 30 hand-built prompts (10 per implicature class); no release statement | **Skip.** It is too small and unreleased. Cite it as related work only. |
| **READI** (Kim et al., Findings of ACL 2026; arXiv:2608.30270) | <https://github.com/jaeheehui/ISA-data> | The repository is **empty** (checked 2026-09-25). 102 multimodal items (45 English). | **Skip.** It is multimodal and unreleased. It is the closest competitor on H1, so re-check it before submission. |
| **MultiWOZ** | see [MultiWOZ 2.1](#multiwoz-21) | MIT | **Downloaded 2026-09-25.** Promoted to a core source by the existing-data design. |
| **SGD** (Rastogi et al., AAAI 2020) | <https://github.com/google-research-datasets/dstc8-schema-guided-dialogue> | CC BY-SA 4.0 | **Keep as reference only.** It is a source of realistic multi-service histories and schemas, and IndirectRequests' upstream. Don't copy its text into the release, because that would force ShareAlike. |
| **SLURP** (Bastianelli et al., EMNLP 2020) | <https://github.com/pswietojanski/slurp> | CC BY 4.0 (text) | **Skip.** MASSIVE en-US already contains its text with intent and slot labels. |
