# Secondary family (Holm-adjusted)

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| name | kind | system | reference | endpoint | contrast | condition | point | ci_low | ci_high | p | p_holm | examples | dialogues | status | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| h1-trend | h1_trend | hybrid |  | request_interpretation |  | none | 0.033 | 0.012 | 0.054 | 0.003 | 0.008 | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| h2-detection-trend | h2_trend | hybrid |  | stage1_correct | full_minus_none |  | 0.000 | -0.008 | 0.009 | 0.940 | 0.940 | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| h4-detection-vs-oracle | h4_contrast | hybrid |  |  |  |  | 0.024 | -0.005 | 0.055 | 0.107 | 0.213 | 1272 | 687 | ok | report.json#provenance (config 231365295e22) |
| full-minus-mismatched | mismatch_control | hybrid |  | request_interpretation | full_minus_mismatched |  | 0.057 | 0.048 | 0.066 | 0.000 | 0.001 | 8285 | 927 | ok | report.json#provenance (config 231365295e22) |
| h3-tfidf-utterance | h3_difference | tfidf-utterance | hybrid | stage1_correct | full_minus_none |  | -0.089 | -0.093 | -0.084 | 0.000 | 0.001 | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| h3-tfidf-context | h3_difference | tfidf-context | hybrid | stage1_correct | full_minus_none |  | -0.079 | -0.084 | -0.073 | 0.000 | 0.001 | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| h3-deberta-v3-base | h3_difference | deberta-v3-base | hybrid | stage1_correct | full_minus_none |  | -0.071 | -0.075 | -0.067 | 0.000 | 0.001 | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| h3-deberta-v3-large | h3_difference | deberta-v3-large | hybrid | stage1_correct | full_minus_none |  | -0.004 | -0.006 | -0.002 | 0.000 | 0.001 | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| h3-qwen2.5-7b-instruct | h3_difference | qwen2.5-7b-instruct | hybrid | request_interpretation | full_minus_none |  | 0.002 | 0.001 | 0.003 | 0.001 | 0.004 | 8317 | 927 | ok | report.json#provenance (config 231365295e22) |
