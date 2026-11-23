# H5 (exploratory): context benefit by intent category

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | line | endpoint | category | contrast | point | ci_low | ci_high | p | p_holm | examples | dialogues | status | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf-utterance | test_time | stage1_correct | booking | full_minus_none | 0.000 | 0.000 | 0.000 |  |  | 1279 | 490 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | info_seeking | full_minus_none | 0.000 | 0.000 | 0.000 |  |  | 2391 | 667 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | no_request | full_minus_none | 0.000 | 0.000 | 0.000 |  |  | 2140 | 858 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | recommendation | full_minus_none | 0.000 | 0.000 | 0.000 |  |  | 2649 | 679 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | travel | full_minus_none | 0.000 | 0.000 | 0.000 |  |  | 2006 | 607 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | booking | full_minus_none | 0.004 | -0.004 | 0.012 |  |  | 1279 | 490 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | info_seeking | full_minus_none | -0.001 | -0.007 | 0.006 |  |  | 2391 | 667 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | no_request | full_minus_none | 0.055 | 0.045 | 0.065 |  |  | 2140 | 858 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | recommendation | full_minus_none | -0.005 | -0.012 | 0.001 |  |  | 2649 | 679 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | travel | full_minus_none | -0.000 | -0.009 | 0.008 |  |  | 2006 | 607 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | booking | full_minus_none | 0.008 | 0.002 | 0.014 |  |  | 1279 | 490 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | info_seeking | full_minus_none | -0.000 | -0.004 | 0.004 |  |  | 2391 | 667 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | no_request | full_minus_none | 0.002 | -0.001 | 0.005 |  |  | 2140 | 858 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | recommendation | full_minus_none | 0.000 | -0.004 | 0.005 |  |  | 2649 | 679 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | travel | full_minus_none | 0.002 | -0.004 | 0.007 |  |  | 2006 | 607 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | booking | full_minus_none | 0.000 | -0.005 | 0.006 |  |  | 1279 | 490 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | info_seeking | full_minus_none | -0.003 | -0.007 | 0.001 |  |  | 2391 | 667 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | no_request | full_minus_none | 0.005 | 0.001 | 0.009 |  |  | 2140 | 858 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | recommendation | full_minus_none | -0.000 | -0.006 | 0.005 |  |  | 2649 | 679 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | travel | full_minus_none | 0.004 | -0.002 | 0.010 |  |  | 2006 | 607 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | booking | full_minus_none | -0.059 | -0.087 | -0.031 |  |  | 1279 | 490 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | info_seeking | full_minus_none | 0.009 | -0.000 | 0.018 |  |  | 2391 | 667 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | recommendation | full_minus_none | 0.041 | 0.025 | 0.058 |  |  | 2641 | 677 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | travel | full_minus_none | 0.000 | -0.023 | 0.023 |  |  | 2006 | 607 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | booking | full_minus_none | -0.059 | -0.087 | -0.031 |  |  | 1279 | 490 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | info_seeking | full_minus_none | 0.008 | -0.001 | 0.017 |  |  | 2391 | 667 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | recommendation | full_minus_none | 0.040 | 0.023 | 0.056 |  |  | 2641 | 677 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | travel | full_minus_none | -0.003 | -0.027 | 0.020 |  |  | 2006 | 607 | ok | report.json#provenance (config 231365295e22) |
