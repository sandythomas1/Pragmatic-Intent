# H3: benefit difference against the primary system (test-time lines)

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | reference | line | endpoint | contrast | level | point | ci_low | ci_high | p | p_holm | examples | dialogues | status | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf-utterance | hybrid | test_time | stage1_correct | full_minus_none | overall | -0.089 | -0.093 | -0.084 | 0.000 |  | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | hybrid | test_time | stage1_correct | full_minus_none | overall | -0.079 | -0.084 | -0.073 | 0.000 |  | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | hybrid | test_time | stage1_correct | full_minus_none | overall | -0.071 | -0.075 | -0.067 | 0.000 |  | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | hybrid | test_time | stage1_correct | full_minus_none | overall | -0.004 | -0.006 | -0.002 | 0.000 |  | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | hybrid | test_time | request_interpretation | full_minus_none | overall | 0.002 | 0.001 | 0.003 | 0.001 |  | 8317 | 927 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | hybrid | test_time | type_exact | full_minus_none | overall | -0.087 | -0.093 | -0.080 |  |  | 10457 | 934 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | hybrid | test_time | stage1_correct | full_minus_none | overall | -0.085 | -0.094 | -0.075 |  |  | 10465 | 934 | ok | report.json#provenance (config 231365295e22) |
