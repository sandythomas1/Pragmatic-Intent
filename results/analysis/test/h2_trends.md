# H2: benefit trends and level − L0 differences

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | line | endpoint | contrast | trend | levels | point | ci_low | ci_high | p | p_holm | examples | dialogues | status | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf-utterance | test_time | stage1_correct | one_minus_none | linear | L0; L1; L2 | 0.000 | 0.000 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | 0.000 | 0.000 | 0.000 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | 0.000 | 0.000 | 0.000 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | 0.000 | 0.000 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | 0.000 | 0.000 | 0.000 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | 0.000 | 0.000 | 0.000 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | 0.000 | 0.000 | 0.000 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.000 | 0.000 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | 0.000 | 0.000 | 0.000 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | 0.000 | 0.000 | 0.000 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.000 | 0.000 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | 0.000 | 0.000 | 0.000 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.000 | 0.000 | 0.000 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | 0.000 | 0.000 | 0.000 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_one | linear | L0; L1; L2 | 0.000 | 0.000 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | 0.000 | 0.000 | 0.000 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | 0.000 | 0.000 | 0.000 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | 0.000 | 0.000 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | 0.000 | 0.000 | 0.000 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | 0.000 | 0.000 | 0.000 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| tfidf-utterance | test_time | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | 0.000 | 0.000 | 0.000 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one_minus_none | linear | L0; L1; L2 | -0.003 | -0.013 | 0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | -0.019 | -0.035 | -0.003 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | 0.008 | 0.000 | 0.016 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | -0.003 | -0.013 | 0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | -0.015 | -0.038 | 0.007 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | -0.042 | -0.078 | -0.009 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | 0.047 | 0.036 | 0.058 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_none | linear | L0; L1; L2 | -0.010 | -0.021 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | -0.007 | -0.022 | 0.008 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | -0.002 | -0.009 | 0.006 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | -0.010 | -0.021 | 0.000 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | -0.024 | -0.048 | -0.001 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | -0.014 | -0.058 | 0.030 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | 0.050 | 0.039 | 0.061 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_one | linear | L0; L1; L2 | -0.008 | -0.018 | 0.003 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | 0.012 | -0.005 | 0.028 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | -0.010 | -0.018 | -0.001 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | -0.008 | -0.018 | 0.003 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | -0.009 | -0.032 | 0.013 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | 0.027 | -0.018 | 0.076 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| tfidf-context | test_time | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | 0.003 | -0.005 | 0.011 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one_minus_none | linear | L0; L1; L2 | -0.001 | -0.008 | 0.005 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | 0.008 | -0.003 | 0.018 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | -0.005 | -0.010 | 0.001 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | -0.001 | -0.008 | 0.005 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | 0.008 | -0.008 | 0.026 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | 0.002 | -0.020 | 0.026 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | 0.001 | -0.004 | 0.006 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.002 | -0.004 | 0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | 0.011 | 0.000 | 0.020 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | -0.004 | -0.009 | 0.001 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.002 | -0.004 | 0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | -0.003 | -0.022 | 0.016 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.008 | -0.019 | 0.037 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | 0.000 | -0.004 | 0.005 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_one | linear | L0; L1; L2 | 0.004 | -0.001 | 0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | 0.003 | -0.006 | 0.011 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | 0.000 | -0.004 | 0.005 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | 0.004 | -0.001 | 0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | -0.012 | -0.027 | 0.004 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | 0.006 | -0.011 | 0.022 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | matched | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | -0.001 | -0.004 | 0.003 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | one_minus_none | linear | L0; L1; L2 | 0.032 | 0.020 | 0.043 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | 0.055 | 0.041 | 0.069 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | -0.012 | -0.018 | -0.005 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | 0.032 | 0.020 | 0.043 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | -0.008 | -0.029 | 0.013 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | 0.043 | 0.001 | 0.087 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | -0.014 | -0.021 | -0.008 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.034 | 0.021 | 0.045 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | 0.056 | 0.042 | 0.070 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | -0.011 | -0.018 | -0.005 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.034 | 0.021 | 0.045 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | -0.021 | -0.040 | -0.002 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.042 | 0.001 | 0.086 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | -0.006 | -0.012 | 0.001 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_one | linear | L0; L1; L2 | 0.002 | -0.002 | 0.005 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | 0.001 | -0.005 | 0.007 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | 0.000 | -0.003 | 0.003 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | 0.002 | -0.002 | 0.005 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | -0.013 | -0.026 | 0.000 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | -0.000 | -0.014 | 0.014 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-base | test_time | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | 0.009 | 0.006 | 0.012 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one_minus_none | linear | L0; L1; L2 | 0.001 | -0.005 | 0.008 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | 0.007 | -0.003 | 0.017 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | -0.003 | -0.008 | 0.002 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | 0.001 | -0.005 | 0.008 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | -0.001 | -0.019 | 0.019 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | 0.014 | -0.009 | 0.039 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | 0.002 | -0.003 | 0.007 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.003 | -0.004 | 0.010 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | 0.011 | -0.000 | 0.023 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | -0.004 | -0.010 | 0.002 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.003 | -0.004 | 0.010 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | -0.014 | -0.033 | 0.008 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.008 | -0.021 | 0.036 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | 0.004 | -0.001 | 0.009 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_one | linear | L0; L1; L2 | 0.002 | -0.004 | 0.007 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | 0.004 | -0.005 | 0.013 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | -0.001 | -0.006 | 0.003 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | 0.002 | -0.004 | 0.007 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | -0.013 | -0.026 | -0.001 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | -0.006 | -0.024 | 0.012 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | matched | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | 0.002 | -0.001 | 0.005 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | one_minus_none | linear | L0; L1; L2 | 0.039 | 0.027 | 0.052 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | 0.081 | 0.065 | 0.096 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | -0.021 | -0.028 | -0.013 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | 0.039 | 0.027 | 0.052 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | -0.029 | -0.052 | -0.006 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | 0.035 | -0.010 | 0.082 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | 0.257 | 0.248 | 0.267 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.040 | 0.027 | 0.053 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | 0.083 | 0.066 | 0.099 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | -0.022 | -0.030 | -0.014 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.040 | 0.027 | 0.053 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | -0.036 | -0.060 | -0.012 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.039 | -0.008 | 0.089 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | 0.264 | 0.254 | 0.273 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_one | linear | L0; L1; L2 | 0.000 | -0.005 | 0.005 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | 0.002 | -0.005 | 0.009 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | -0.001 | -0.005 | 0.003 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | 0.000 | -0.005 | 0.005 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | -0.007 | -0.018 | 0.005 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | 0.004 | -0.010 | 0.020 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| deberta-v3-large | test_time | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | 0.006 | 0.003 | 0.010 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | linear | L0; L1; L2 | 0.009 | -0.010 | 0.028 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | quadratic | L0; L1; L2 | 0.018 | -0.018 | 0.054 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | level_minus_L0 | L1; L0 | -0.005 | -0.023 | 0.013 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | level_minus_L0 | L2; L0 | 0.009 | -0.010 | 0.028 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | level_minus_L0 | L3; L0 | 0.010 | -0.021 | 0.041 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | level_minus_L0 | INF; L0 | -0.024 | -0.076 | 0.027 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | one_minus_none | level_minus_L0 | NR; L0 | -0.148 | -0.252 | -0.052 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_none | linear | L0; L1; L2 | -0.006 | -0.029 | 0.017 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_none | quadratic | L0; L1; L2 | 0.018 | -0.021 | 0.057 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_none | level_minus_L0 | L1; L0 | -0.012 | -0.031 | 0.007 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_none | level_minus_L0 | L2; L0 | -0.006 | -0.029 | 0.017 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_none | level_minus_L0 | L3; L0 | 0.036 | -0.000 | 0.074 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_none | level_minus_L0 | INF; L0 | 0.001 | -0.053 | 0.056 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_none | level_minus_L0 | NR; L0 | -0.127 | -0.227 | -0.032 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | linear | L0; L1; L2 | -0.015 | -0.036 | 0.006 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | quadratic | L0; L1; L2 | -0.000 | -0.037 | 0.037 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | level_minus_L0 | L1; L0 | -0.008 | -0.026 | 0.011 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | level_minus_L0 | L2; L0 | -0.015 | -0.036 | 0.006 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | level_minus_L0 | L3; L0 | 0.026 | -0.007 | 0.061 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | level_minus_L0 | INF; L0 | 0.025 | -0.029 | 0.079 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | request_interpretation | full_minus_one | level_minus_L0 | NR; L0 | 0.021 | -0.063 | 0.107 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one_minus_none | linear | L0; L1; L2 | 0.005 | -0.013 | 0.023 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one_minus_none | quadratic | L0; L1; L2 | -0.048 | -0.083 | -0.012 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one_minus_none | level_minus_L0 | L1; L0 | 0.026 | 0.008 | 0.045 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one_minus_none | level_minus_L0 | L2; L0 | 0.005 | -0.013 | 0.023 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one_minus_none | level_minus_L0 | L3; L0 | 0.014 | -0.012 | 0.041 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one_minus_none | level_minus_L0 | INF; L0 | -0.005 | -0.047 | 0.037 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | one_minus_none | level_minus_L0 | NR; L0 | -0.025 | -0.037 | -0.013 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | linear | L0; L1; L2 | 0.010 | -0.010 | 0.029 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | quadratic | L0; L1; L2 | -0.057 | -0.094 | -0.019 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | level_minus_L0 | L1; L0 | 0.033 | 0.013 | 0.053 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | level_minus_L0 | L2; L0 | 0.010 | -0.010 | 0.029 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | level_minus_L0 | L3; L0 | 0.035 | 0.010 | 0.062 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | level_minus_L0 | INF; L0 | 0.033 | -0.012 | 0.079 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_none | level_minus_L0 | NR; L0 | -0.064 | -0.080 | -0.047 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | linear | L0; L1; L2 | 0.005 | -0.013 | 0.023 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | quadratic | L0; L1; L2 | -0.009 | -0.043 | 0.024 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | level_minus_L0 | L1; L0 | 0.007 | -0.011 | 0.025 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | level_minus_L0 | L2; L0 | 0.005 | -0.013 | 0.023 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | level_minus_L0 | L3; L0 | 0.022 | -0.006 | 0.049 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | level_minus_L0 | INF; L0 | 0.038 | -0.003 | 0.081 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | type_exact | full_minus_one | level_minus_L0 | NR; L0 | -0.039 | -0.053 | -0.025 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one_minus_none | linear | L0; L1; L2 | 0.041 | 0.017 | 0.066 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | -0.042 | -0.097 | 0.013 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | 0.042 | 0.013 | 0.071 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | 0.041 | 0.017 | 0.066 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | 0.051 | 0.002 | 0.101 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | -0.071 | -0.143 | 0.000 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | -0.015 | -0.030 | 0.001 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.059 | 0.034 | 0.084 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | -0.094 | -0.157 | -0.030 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | 0.076 | 0.042 | 0.110 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.059 | 0.034 | 0.084 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | 0.056 | 0.003 | 0.108 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.004 | -0.063 | 0.073 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | -0.060 | -0.079 | -0.041 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_one | linear | L0; L1; L2 | 0.017 | -0.004 | 0.038 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | -0.052 | -0.100 | -0.002 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | 0.034 | 0.009 | 0.060 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | 0.017 | -0.004 | 0.038 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | 0.005 | -0.040 | 0.049 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | 0.075 | 0.016 | 0.135 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| qwen2.5-7b-instruct | test_time | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | -0.046 | -0.062 | -0.029 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one_minus_none | linear | L0; L1; L2 | 0.008 | -0.010 | 0.027 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one_minus_none | quadratic | L0; L1; L2 | 0.021 | -0.015 | 0.057 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one_minus_none | level_minus_L0 | L1; L0 | -0.007 | -0.025 | 0.011 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one_minus_none | level_minus_L0 | L2; L0 | 0.008 | -0.010 | 0.027 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one_minus_none | level_minus_L0 | L3; L0 | 0.009 | -0.023 | 0.042 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one_minus_none | level_minus_L0 | INF; L0 | -0.026 | -0.078 | 0.025 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | one_minus_none | level_minus_L0 | NR; L0 | -0.150 | -0.254 | -0.054 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_none | linear | L0; L1; L2 | -0.005 | -0.027 | 0.018 | 0.686 |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_none | quadratic | L0; L1; L2 | 0.019 | -0.020 | 0.057 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_none | level_minus_L0 | L1; L0 | -0.012 | -0.031 | 0.008 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_none | level_minus_L0 | L2; L0 | -0.005 | -0.027 | 0.018 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_none | level_minus_L0 | L3; L0 | 0.037 | 0.001 | 0.074 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_none | level_minus_L0 | INF; L0 | 0.003 | -0.051 | 0.058 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_none | level_minus_L0 | NR; L0 | -0.125 | -0.225 | -0.030 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_one | linear | L0; L1; L2 | -0.013 | -0.033 | 0.008 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_one | quadratic | L0; L1; L2 | -0.003 | -0.040 | 0.034 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_one | level_minus_L0 | L1; L0 | -0.005 | -0.023 | 0.014 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_one | level_minus_L0 | L2; L0 | -0.013 | -0.033 | 0.008 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_one | level_minus_L0 | L3; L0 | 0.028 | -0.005 | 0.061 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_one | level_minus_L0 | INF; L0 | 0.029 | -0.025 | 0.083 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | request_interpretation | full_minus_one | level_minus_L0 | NR; L0 | 0.025 | -0.059 | 0.111 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one_minus_none | linear | L0; L1; L2 | 0.006 | -0.011 | 0.023 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one_minus_none | quadratic | L0; L1; L2 | 0.021 | -0.014 | 0.056 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one_minus_none | level_minus_L0 | L1; L0 | -0.008 | -0.025 | 0.010 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one_minus_none | level_minus_L0 | L2; L0 | 0.006 | -0.011 | 0.023 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one_minus_none | level_minus_L0 | L3; L0 | 0.000 | -0.030 | 0.031 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one_minus_none | level_minus_L0 | INF; L0 | -0.024 | -0.075 | 0.025 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | one_minus_none | level_minus_L0 | NR; L0 | -0.019 | -0.030 | -0.008 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_none | linear | L0; L1; L2 | -0.005 | -0.026 | 0.017 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_none | quadratic | L0; L1; L2 | 0.021 | -0.015 | 0.059 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_none | level_minus_L0 | L1; L0 | -0.013 | -0.032 | 0.005 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_none | level_minus_L0 | L2; L0 | -0.005 | -0.026 | 0.017 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_none | level_minus_L0 | L3; L0 | 0.035 | 0.001 | 0.070 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_none | level_minus_L0 | INF; L0 | -0.002 | -0.051 | 0.048 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_none | level_minus_L0 | NR; L0 | -0.007 | -0.019 | 0.006 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_one | linear | L0; L1; L2 | -0.011 | -0.030 | 0.009 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_one | quadratic | L0; L1; L2 | -0.000 | -0.036 | 0.035 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_one | level_minus_L0 | L1; L0 | -0.005 | -0.023 | 0.013 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_one | level_minus_L0 | L2; L0 | -0.011 | -0.030 | 0.009 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_one | level_minus_L0 | L3; L0 | 0.035 | 0.004 | 0.067 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_one | level_minus_L0 | INF; L0 | 0.023 | -0.027 | 0.073 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | type_exact | full_minus_one | level_minus_L0 | NR; L0 | 0.012 | 0.001 | 0.024 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one_minus_none | linear | L0; L1; L2 | 0.002 | -0.006 | 0.010 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | 0.002 | -0.012 | 0.016 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | -0.000 | -0.008 | 0.007 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | 0.002 | -0.006 | 0.010 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | -0.001 | -0.022 | 0.022 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | 0.017 | -0.009 | 0.044 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | -0.001 | -0.007 | 0.004 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.000 | -0.008 | 0.009 | 0.940 |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | 0.003 | -0.013 | 0.018 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | -0.001 | -0.009 | 0.007 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.000 | -0.008 | 0.009 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | -0.013 | -0.034 | 0.011 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.009 | -0.021 | 0.039 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | -0.001 | -0.007 | 0.005 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_one | linear | L0; L1; L2 | -0.002 | -0.008 | 0.004 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | 0.000 | -0.011 | 0.012 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | -0.001 | -0.007 | 0.005 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | -0.002 | -0.008 | 0.004 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | -0.012 | -0.026 | 0.002 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | -0.008 | -0.026 | 0.011 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | 0.000 | -0.004 | 0.004 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | one_minus_none | linear | L0; L1; L2 | 0.008 | -0.011 | 0.027 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | one_minus_none | quadratic | L0; L1; L2 | 0.020 | -0.016 | 0.057 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | one_minus_none | level_minus_L0 | L1; L0 | -0.006 | -0.024 | 0.012 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | one_minus_none | level_minus_L0 | L2; L0 | 0.008 | -0.011 | 0.027 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | one_minus_none | level_minus_L0 | L3; L0 | 0.010 | -0.022 | 0.042 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | one_minus_none | level_minus_L0 | INF; L0 | -0.023 | -0.075 | 0.027 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | one_minus_none | level_minus_L0 | NR; L0 | -0.150 | -0.253 | -0.054 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_none | linear | L0; L1; L2 | -0.005 | -0.027 | 0.018 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_none | quadratic | L0; L1; L2 | 0.018 | -0.020 | 0.057 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_none | level_minus_L0 | L1; L0 | -0.012 | -0.031 | 0.008 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_none | level_minus_L0 | L2; L0 | -0.005 | -0.027 | 0.018 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_none | level_minus_L0 | L3; L0 | 0.038 | 0.003 | 0.074 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_none | level_minus_L0 | INF; L0 | 0.005 | -0.048 | 0.059 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_none | level_minus_L0 | NR; L0 | -0.125 | -0.225 | -0.030 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_one | linear | L0; L1; L2 | -0.013 | -0.033 | 0.008 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_one | quadratic | L0; L1; L2 | -0.002 | -0.039 | 0.035 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_one | level_minus_L0 | L1; L0 | -0.005 | -0.024 | 0.013 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_one | level_minus_L0 | L2; L0 | -0.013 | -0.033 | 0.008 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_one | level_minus_L0 | L3; L0 | 0.028 | -0.005 | 0.061 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_one | level_minus_L0 | INF; L0 | 0.028 | -0.025 | 0.083 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | request_interpretation | full_minus_one | level_minus_L0 | NR; L0 | 0.024 | -0.059 | 0.111 |  |  | 77 | 74 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | one_minus_none | linear | L0; L1; L2 | 0.018 | 0.000 | 0.036 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | one_minus_none | quadratic | L0; L1; L2 | 0.048 | 0.013 | 0.082 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | one_minus_none | level_minus_L0 | L1; L0 | -0.015 | -0.033 | 0.003 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | one_minus_none | level_minus_L0 | L2; L0 | 0.018 | 0.000 | 0.036 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | one_minus_none | level_minus_L0 | L3; L0 | -0.010 | -0.040 | 0.021 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | one_minus_none | level_minus_L0 | INF; L0 | -0.029 | -0.078 | 0.020 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | one_minus_none | level_minus_L0 | NR; L0 | 0.251 | 0.237 | 0.264 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_none | linear | L0; L1; L2 | 0.008 | -0.013 | 0.029 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_none | quadratic | L0; L1; L2 | 0.045 | 0.009 | 0.083 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_none | level_minus_L0 | L1; L0 | -0.019 | -0.037 | -0.000 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_none | level_minus_L0 | L2; L0 | 0.008 | -0.013 | 0.029 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_none | level_minus_L0 | L3; L0 | 0.027 | -0.008 | 0.063 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_none | level_minus_L0 | INF; L0 | -0.008 | -0.056 | 0.042 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_none | level_minus_L0 | NR; L0 | 0.269 | 0.256 | 0.283 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_one | linear | L0; L1; L2 | -0.010 | -0.030 | 0.010 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_one | quadratic | L0; L1; L2 | -0.003 | -0.038 | 0.033 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_one | level_minus_L0 | L1; L0 | -0.004 | -0.022 | 0.014 |  |  | 1759 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_one | level_minus_L0 | L2; L0 | -0.010 | -0.030 | 0.010 |  |  | 2137 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_one | level_minus_L0 | L3; L0 | 0.037 | 0.006 | 0.068 |  |  | 323 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_one | level_minus_L0 | INF; L0 | 0.021 | -0.028 | 0.071 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | type_exact | full_minus_one | level_minus_L0 | NR; L0 | 0.019 | 0.007 | 0.030 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | one_minus_none | linear | L0; L1; L2 | 0.040 | 0.027 | 0.053 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | one_minus_none | quadratic | L0; L1; L2 | 0.076 | 0.057 | 0.095 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | one_minus_none | level_minus_L0 | L1; L0 | -0.018 | -0.027 | -0.009 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | one_minus_none | level_minus_L0 | L2; L0 | 0.040 | 0.027 | 0.053 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | one_minus_none | level_minus_L0 | L3; L0 | -0.029 | -0.054 | -0.003 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | one_minus_none | level_minus_L0 | INF; L0 | 0.037 | -0.008 | 0.086 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | one_minus_none | level_minus_L0 | NR; L0 | 0.255 | 0.245 | 0.264 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_none | linear | L0; L1; L2 | 0.037 | 0.023 | 0.051 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_none | quadratic | L0; L1; L2 | 0.074 | 0.054 | 0.094 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_none | level_minus_L0 | L1; L0 | -0.018 | -0.028 | -0.008 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_none | level_minus_L0 | L2; L0 | 0.037 | 0.023 | 0.051 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_none | level_minus_L0 | L3; L0 | -0.035 | -0.060 | -0.008 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_none | level_minus_L0 | INF; L0 | 0.040 | -0.009 | 0.091 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_none | level_minus_L0 | NR; L0 | 0.259 | 0.249 | 0.268 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_one | linear | L0; L1; L2 | -0.003 | -0.009 | 0.002 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_one | quadratic | L0; L1; L2 | -0.002 | -0.013 | 0.008 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_one | level_minus_L0 | L1; L0 | -0.001 | -0.006 | 0.005 |  |  | 1762 | 779 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_one | level_minus_L0 | L2; L0 | -0.003 | -0.009 | 0.002 |  |  | 2139 | 797 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_one | level_minus_L0 | L3; L0 | -0.006 | -0.019 | 0.008 |  |  | 324 | 252 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_one | level_minus_L0 | INF; L0 | 0.003 | -0.012 | 0.018 |  |  | 178 | 158 | ok | report.json#provenance (config 231365295e22) |
| hybrid | test_time | stage1_correct | full_minus_one | level_minus_L0 | NR; L0 | 0.004 | -0.000 | 0.009 |  |  | 2217 | 862 | ok | report.json#provenance (config 231365295e22) |
