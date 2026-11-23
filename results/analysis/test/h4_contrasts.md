# H4: drop(detection) − drop(oracle) under full

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | line | condition | definition | point | ci_low | ci_high | p | p_holm | examples | dialogues | status | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-7b-instruct | test_time | full | drop(detection) - drop(oracle), drop = rate_L0 - rate_L2 | 0.022 | -0.009 | 0.052 |  |  | 1272 | 687 | ok | report.json#provenance (config 231365295e22) |
| hybrid | matched | full | drop(detection) - drop(oracle), drop = rate_L0 - rate_L2 | 0.024 | -0.005 | 0.055 | 0.107 |  | 1272 | 687 | ok | report.json#provenance (config 231365295e22) |
