# Verification: Spec 006

_Real-data smoke check, 2026-10-19, native Windows, Python 3.12. Every real-data command's
console output was piped through a filter that masked dialogue IDs, so no test ID or text was
printed in the session (working rule, spec 006)._

## Commands and results

| Step | Command | Result |
|---|---|---|
| Derived rows | `python -m src.data.split_audit register` | 48 rows, 47 test dialogues. Both pinned local sources still match their SHA-256 (otherwise `register` refuses). |
| Session logs | `scan --transcripts <Claude Code project dir> <~/.codex/sessions> --register --on 2026-10-19` | 22 log files read, 22 test dialogues mentioned, 4 not already registered. 22 `claude_session` rows written. |
| Idempotence | `register` again | 70 rows, 51 dialogues, 0 added. |
| Sheets | `scan` | 20 files scanned (2 `.xlsx` skipped, covered by their `_items.csv`), 5 hold test dialogues, all registered. Exit 0. |
| Splits | `check` | All six rules pass on 1,000 test dialogues. 5 test dialogues duplicate a train/dev dialogue (0.50%); 2 dev↔train duplicates (reported only). Exit 0. |
| Audit | `audit` | Built in a few seconds. Content hash `432e402c841b…`. |
| Reproduction | `audit --verify` | Both files match a fresh build byte for byte. Exit 0. |
| Leak check | A seeded sample of 500 test utterances and slot values; 412 probes of at least 12 characters | 0 found in the registry, audit or summary. All three files hold only ID, code, number and hash characters. |
| Tests | `python -m unittest discover -s tests` | All pass (see the final count in tasks.md T9). |

## Registry (AC-006-11)

| Source | Test dialogues | Note |
|---|---|---|
| `levels_round1` + `levels_round3` | 13 | Calibration labels. |
| `obsolete_round3_sheet` | 10 | Claude's sealed labels on the test-drawn sheet. |
| `fact_drift_review` | 24 new (25 total) | One overlaps round 1. |
| `claude_session` | 4 new (22 total) | Hits in the Claude Code and Codex logs. |
| **Total `pre_freeze`** | **51** | The spec expected 49. |

**Why 51, not 49.** The two extra session-log dialogues were explained without printing any ID:

1. Two dialogues are mentioned in an Oct 1 session only inside DIRECT item IDs (`<ID>_t02`). The
   spec's earlier ad-hoc count evidently used a word-boundary pattern, which cannot match before
   `_`. The tool's boundary-safe pattern (decisions.md, T2–T4) finds them.
2. The spec's two counted hits are an Oct 1 `.json` mention and one ID printed in this session's
   `testListFile` slip (2026-10-19). Claude had also reused that ID as a fixture in the T1 tests.
   The fixture now uses invented IDs, and the dialogue is registered.

Under the conservative session-log policy (Sandy approved R2), all four are registered.

## Audit summary (FR10–FR12)

| Measure | Value |
|---|---|
| Test dialogues / items / genuine examples / mismatch examples | 1,000 / 7,372 / 11,195 / 11,123 |
| Excluded dialogues by reason | calibration 13, sealed 10, fact-drift 24, session 4, cross-split duplicate 5 (**56**) |
| Excluded genuine examples by reason | calibration 169, sealed 115, fact-drift 258, session 35, cross-split duplicate 33 (**610**) |
| Primary set | **10,585 genuine, 10,513 mismatch** |
| `dup_exact` among primary examples | 1,585 (15.0%): direct 16.5%, indirect 13.4%. By `auto-v1` level: NR 48.2% (templated thanks/bye lines), L0 9.1%, L1 5.0%, L3 4.6%, L2 2.1%, INF 0% |
| Excluded test items by reason | calibration 105, sealed 71, fact-drift 170, session 22, cross-split duplicate 25 (393) |
| Primary examples with an inspected donor (`donor_inspected`) | 495 (disclosed only) |
| `needs_decision` | false (0.50% ≤ 1%) |
| `post_scoring` dialogues | 0 |

## Deviations from the plan

- **The scan reads every CSV cell, including cells beyond the header.** The local
  `round3_claude_sealed.csv` has one ragged row. A malformed CSV still fails the scan.
- **A spec 003 blind sheet may be keyed by `<sheet>_sheet_info.json`, not only `key.csv`.** This
  covers `pilot1/form_A1.csv`, whose 40 dev items are in `form_A1_sheet_info.json`. That file is
  scanned too.
- **No build timestamp in the summary.** Both files are fully deterministic, so `--verify` compares
  them byte for byte.

## For Sandy (WSL, before the freeze)

```bash
cd ~/Pragmatic-Intent && git pull
uv run python -m src.data.split_audit audit --verify   # must print "match a fresh build"; exit 0
```

If it fails, the WSL `items.jsonl`/`dialogues.jsonl` bytes differ from Windows. Report it: the
build gets fixed, and the check is never loosened (AC-006-11). Rerun the transcript scan once,
immediately before the freeze, and rebuild the audit if it adds rows.
