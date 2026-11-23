# H1: L0–L2 linear trend of success

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | line | endpoint | condition | trend | levels | point | ci_low | ci_high | p | p_holm | examples | dialogues | status | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf-utterance | test_time | stage1_correct | none | linear | L0; L1; L2 | -0.058 | -0.077 | -0.040 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | one | linear | L0; L1; L2 | -0.058 | -0.077 | -0.040 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full | linear | L0; L1; L2 | -0.058 | -0.077 | -0.040 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | mismatched | linear | L0; L1; L2 | -0.059 | -0.078 | -0.041 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | mismatched_one | linear | L0; L1; L2 | -0.059 | -0.078 | -0.041 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | none | linear | L0; L1; L2 | -0.060 | -0.078 | -0.042 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one | linear | L0; L1; L2 | -0.063 | -0.081 | -0.044 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full | linear | L0; L1; L2 | -0.070 | -0.089 | -0.052 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | mismatched | linear | L0; L1; L2 | -0.074 | -0.094 | -0.056 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | mismatched_one | linear | L0; L1; L2 | -0.067 | -0.086 | -0.049 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | none | linear | L0; L1; L2 | -0.032 | -0.047 | -0.017 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one | linear | L0; L1; L2 | -0.033 | -0.048 | -0.018 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full | linear | L0; L1; L2 | -0.029 | -0.044 | -0.015 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | mismatched | linear | L0; L1; L2 | -0.057 | -0.072 | -0.041 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | mismatched_one | linear | L0; L1; L2 | -0.058 | -0.074 | -0.043 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | none | linear | L0; L1; L2 | -0.028 | -0.042 | -0.014 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one | linear | L0; L1; L2 | -0.027 | -0.041 | -0.012 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full | linear | L0; L1; L2 | -0.025 | -0.039 | -0.011 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | mismatched | linear | L0; L1; L2 | -0.063 | -0.079 | -0.047 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | mismatched_one | linear | L0; L1; L2 | -0.062 | -0.077 | -0.047 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | none | linear | L0; L1; L2 | 0.035 | 0.014 | 0.056 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one | linear | L0; L1; L2 | 0.044 | 0.021 | 0.067 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full | linear | L0; L1; L2 | 0.029 | 0.007 | 0.051 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | mismatched | linear | L0; L1; L2 | -0.001 | -0.019 | 0.018 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | mismatched_one | linear | L0; L1; L2 | 0.018 | -0.001 | 0.037 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | none | linear | L0; L1; L2 | 0.002 | -0.015 | 0.019 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one | linear | L0; L1; L2 | 0.007 | -0.011 | 0.025 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full | linear | L0; L1; L2 | 0.012 | -0.006 | 0.029 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | mismatched | linear | L0; L1; L2 | 0.004 | -0.009 | 0.017 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | mismatched_one | linear | L0; L1; L2 | 0.008 | -0.006 | 0.023 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | none | linear | L0; L1; L2 | -0.139 | -0.163 | -0.114 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one | linear | L0; L1; L2 | -0.097 | -0.122 | -0.072 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full | linear | L0; L1; L2 | -0.080 | -0.105 | -0.054 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | mismatched | linear | L0; L1; L2 | 0.076 | 0.050 | 0.100 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | mismatched_one | linear | L0; L1; L2 | -0.020 | -0.044 | 0.005 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | none | linear | L0; L1; L2 | 0.033 | 0.012 | 0.054 | 0.003 |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one | linear | L0; L1; L2 | 0.041 | 0.019 | 0.064 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full | linear | L0; L1; L2 | 0.028 | 0.006 | 0.051 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | mismatched | linear | L0; L1; L2 | -0.001 | -0.019 | 0.017 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | mismatched_one | linear | L0; L1; L2 | 0.014 | -0.005 | 0.034 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | none | linear | L0; L1; L2 | 0.024 | 0.004 | 0.044 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one | linear | L0; L1; L2 | 0.030 | 0.009 | 0.051 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full | linear | L0; L1; L2 | 0.019 | -0.002 | 0.040 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | mismatched | linear | L0; L1; L2 | -0.016 | -0.032 | 0.000 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | mismatched_one | linear | L0; L1; L2 | -0.004 | -0.021 | 0.014 |  |  | 2128 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | none | linear | L0; L1; L2 | -0.024 | -0.038 | -0.010 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one | linear | L0; L1; L2 | -0.022 | -0.036 | -0.007 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full | linear | L0; L1; L2 | -0.024 | -0.038 | -0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | mismatched | linear | L0; L1; L2 | -0.061 | -0.078 | -0.044 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | mismatched_one | linear | L0; L1; L2 | -0.060 | -0.076 | -0.043 |  |  | 2130 | 797 | ok | report.json#provenance (config 231365295e22) |
