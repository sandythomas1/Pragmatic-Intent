# H5: categories excluded from the standardized line

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | endpoint | included | excluded | excluded_share |
|---|---|---|---|---|
| tfidf-utterance | stage1_correct | booking; info_seeking; recommendation; travel |  | 0.000 |
| tfidf-context | stage1_correct | booking; info_seeking; recommendation; travel |  | 0.000 |
| deberta-v3-base | stage1_correct | booking; info_seeking; recommendation; travel |  | 0.000 |
| deberta-v3-large | stage1_correct | booking; info_seeking; recommendation; travel |  | 0.000 |
| qwen2.5-7b-instruct | request_interpretation | booking; info_seeking; recommendation; travel |  | 0.000 |
| hybrid | request_interpretation | booking; info_seeking; recommendation; travel |  | 0.000 |
