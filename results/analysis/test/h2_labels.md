# H2: main effects without an interaction (AC-09)

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | line | endpoint | contrast | label |
|---|---|---|---|---|
| tfidf-context | test_time | stage1_correct | one_minus_none | main effect, no interaction |
| tfidf-context | test_time | stage1_correct | full_minus_none | main effect, no interaction |
| tfidf-context | test_time | stage1_correct | full_minus_one | main effect, no interaction |
| deberta-v3-large | matched | stage1_correct | one_minus_none | main effect, no interaction |
| deberta-v3-large | matched | stage1_correct | full_minus_one | main effect, no interaction |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | main effect, no interaction |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | main effect, no interaction |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | main effect, no interaction |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | main effect, no interaction |
| hybrid | matched | request_interpretation | one_minus_none | main effect, no interaction |
| hybrid | matched | request_interpretation | full_minus_one | main effect, no interaction |
| hybrid | matched | type_exact | one_minus_none | main effect, no interaction |
| hybrid | matched | type_exact | full_minus_one | main effect, no interaction |
| hybrid | matched | stage1_correct | one_minus_none | main effect, no interaction |
| hybrid | matched | stage1_correct | full_minus_none | main effect, no interaction |
| hybrid | test_time | request_interpretation | one_minus_none | main effect, no interaction |
| hybrid | test_time | request_interpretation | full_minus_one | main effect, no interaction |
| hybrid | test_time | type_exact | full_minus_none | main effect, no interaction |
| hybrid | test_time | type_exact | full_minus_one | main effect, no interaction |
| hybrid | test_time | stage1_correct | full_minus_one | main effect, no interaction |
