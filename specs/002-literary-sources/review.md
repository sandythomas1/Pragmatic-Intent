# Review: Spec 002

Verdict: READY (after revisions R1–R5 below were applied to spec.md on 2026-10-10)

Initial verdict was NEEDS REVISION. Two blocking findings (R1, R2) and three non-blocking ones were
applied directly, because each had an obvious fix inside the spec's existing scope.

## Findings

1. **R1 (blocking, clarity): `include` was undefined.** A screener could read `include` as "this
   is a request" and quietly do the contextual-function annotation (spec 003's pass 2) during
   screening. That would also drop authentic non-requests, which are needed for the false-positive
   endpoint. *Fix:* define `include` as "an eligible addressed exchange with source-grounded prior
   context, carried into annotation whether or not it turns out to be a request". Function is
   not judged here.
2. **R2 (blocking, selection transparency): there was no way to add a missed utterance.** The
   mechanical proposers miss speech: KJV speech without a listed verb, and Aesop speech without
   quotes. If the screener couldn't add those, "exhaustive within family" would be false. If they
   added them off-book, selection would be invisible. *Fix:* sheet rows with a blank
   `candidate_id` are manual additions, allowed only in dev families. Export assigns their ID from
   the resolved span, and the committed log gains `origin` ∈ {`proposed`, `manual`}.
3. **R3 (non-blocking, efficiency): uniform draws over all fables waste picks.** Some fables
   contain no speech at all (e.g. The Goose That Laid the Golden Eggs). *Fix:* the draw pool is
   unassigned episodes with ≥1 mechanical proposal. This is an observable, model-independent
   property, and the pool size is recorded in the families file.
4. **R4 (non-blocking, recall): the KJV speech-verb list was narrow.** It missed `saying`, `told`,
   `prayed` and `spoken`. *Fix:* the list is extended. Residual misses are covered by R2.
5. **R5 (non-blocking, determinism): committed row order was unspecified.** *Fix:* rows are
   sorted by source, then episode order in the text, then target start.

## Non-Issues Considered

- **Committed text exposure:** committed CSVs hold offsets and hashes, and speaker/addressee are
  bounded short role names. AC-002-9 tests this. Fine.
- **Downloader security:** no new network code. The host allowlist is extended by one exact host
  with no wildcard. The cache URL serves 200 directly, so the redirect allowlist is unaffected.
- **Offset stability:** raw decoded offsets plus per-row `source_sha256` and `target_sha256`
  detect any parser or file drift during `validate`.
- **KJV random draws:** deliberately not offered as the default. Random chapters would be mostly
  genealogy or law. KJV families are explicit `assign`s with logged reasons, which is a
  researcher selection, and the paper must disclose it as such. Spec 001 already permits screened
  explicit candidates (John 2).
- **Cross-chapter speech:** a target must resolve within one episode. Rare cross-chapter cases are
  excluded with a reason rather than given a special path (YAGNI).
- **CSV formula injection:** handled by the escape-on-write rule. Excel drops a leading `'` on save,
  so read-back stripping is symmetric.
- **Constitution consistency:** stdlib only, text-free commits, human-only judgments, and no
  model-dependent selection. No conflicts.
