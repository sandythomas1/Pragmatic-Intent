# H5 sensitivity: intent-standardized H2 line

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | line | endpoint | level | kind | point | ci_low | ci_high | p | p_holm | examples | dialogues | status | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf-utterance | test_time | stage1_correct | L0 | standardized_benefit | 0.000 | 0.000 | 0.000 |  |  | 547 | 381 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | L1 | standardized_benefit | 0.000 | 0.000 | 0.000 |  |  | 300 | 255 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | L2 | standardized_benefit | 0.000 | 0.000 | 0.000 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | trend | standardized_linear_trend | 0.000 | 0.000 | 0.000 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | L0 | standardized_benefit | 0.003 | -0.002 | 0.008 |  |  | 547 | 381 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | L1 | standardized_benefit | 0.001 | -0.005 | 0.007 |  |  | 300 | 255 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | L2 | standardized_benefit | -0.009 | -0.018 | -0.000 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | trend | standardized_linear_trend | -0.012 | -0.022 | -0.002 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | L0 | standardized_benefit | 0.002 | -0.001 | 0.005 |  |  | 547 | 381 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | L1 | standardized_benefit | -0.002 | -0.007 | 0.002 |  |  | 300 | 255 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | L2 | standardized_benefit | 0.005 | -0.001 | 0.010 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | trend | standardized_linear_trend | 0.003 | -0.004 | 0.009 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | L0 | standardized_benefit | 0.001 | -0.003 | 0.005 |  |  | 547 | 381 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | L1 | standardized_benefit | -0.004 | -0.008 | 0.001 |  |  | 300 | 255 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | L2 | standardized_benefit | 0.004 | -0.002 | 0.010 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | trend | standardized_linear_trend | 0.002 | -0.005 | 0.010 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | L0 | standardized_benefit | 0.010 | -0.003 | 0.022 |  |  | 547 | 381 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | L1 | standardized_benefit | -0.001 | -0.018 | 0.016 |  |  | 300 | 255 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | L2 | standardized_benefit | 0.006 | -0.011 | 0.023 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | trend | standardized_linear_trend | -0.003 | -0.024 | 0.018 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | L0 | standardized_benefit | 0.007 | -0.005 | 0.020 |  |  | 547 | 381 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | L1 | standardized_benefit | -0.003 | -0.020 | 0.014 |  |  | 300 | 255 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | L2 | standardized_benefit | 0.005 | -0.011 | 0.022 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | trend | standardized_linear_trend | -0.002 | -0.023 | 0.019 |  |  | 307 | 233 | ok | report.json#provenance (config 231365295e22) |
