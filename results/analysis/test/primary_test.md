# Primary test (confirmatory H2)

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.
> The linear contrast weights L0 −1, L1 0, L2 +1: it is the L2 − L0 benefit difference; the quadratic contrast is descriptive.

| label | system | line | endpoint | contrast | weights | status | point | ci_low | ci_high | p | decision | quadratic_point | quadratic_ci_low | quadratic_ci_high | examples | dialogues | provenance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L2 − L0 benefit difference (linear contrast) | hybrid | matched | request_interpretation | full_minus_none | -1; 0; 1 | ok | -0.005 | -0.027 | 0.018 | 0.686 | interval_includes_0 | 0.019 | -0.020 | 0.057 | 2137 | 797 | report.json#provenance (config 231365295e22) |
