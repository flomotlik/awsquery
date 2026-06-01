---
id: sue5t
title: Fix Tags$ default filters and add additive +Column syntax
status: done
priority: high
labels:
- bug
- enhancement
- filters
- cli
remote:
- source: github
  id: '13'
  url: https://github.com/flomotlik/awsquery/issues/13
---

## Context

awsquery ships default column filters in `src/awsquery/default_filters.yaml` so that common services like `ec2 describe-instances` produce a readable, useful table without the user having to specify columns. Two problems with the current state:

### 1. `Tags$` suffix-match is broken for the actual tag we care about

The filter grammar in `src/awsquery/filters.py` treats a trailing `$` as the suffix-anchor in `parse_filter_pattern`. After `transform_tags_structure` in `formatters.py` rewrites the AWS `[{Key, Value}, ...]` shape into `Tags.<TagName>` keys, the columns visible to the filter are `Tags.Name`, `Tags.Environment`, etc. — **not** plain `Tags`.

- `Tags$` matches a column literally named `Tags` (rare — only when transformation didn't happen) and never matches `Tags.Name`.
- Concrete user-facing effect: `awsquery ec2 describe-instances` and `awsquery ec2 describe-vpcs` show empty/missing Name columns despite `Tags$` being in the defaults.

Confirmed offenders so far:
- `default_filters.yaml:1071` (`Tags$`)
- `default_filters.yaml:1087` (`imageTags$`)
- `default_filters.yaml:2230` (`Tags$`)
- `default_filters.yaml:2241` (`Tags$`)

There are ~1961 `$`-suffix entries total — the audit must walk every one and classify *correct* (e.g. `Id$` matching a real top-level field) vs *broken* (anchoring against a key the user can never see post-transformation).

### 2. No additive default-filter syntax

`apply_default_filters` in `src/awsquery/config.py:55` returns `user_columns` directly the moment the user supplies any column:

```python
def apply_default_filters(service, action, user_columns=None):
    if user_columns:
        return user_columns
    defaults = get_default_columns(service, action)
    ...
```

There is no way to say "use the curated defaults *and also* one extra column". User believed this existed historically; it does not.

Proposed CLI: a `+Column` prefix means *additive* — keep the defaults from `default_filters.yaml` and merge in the user's extra columns. Bare `Column` (no `+`) keeps today's replace-defaults behaviour. The merge needs to dedupe and preserve order.

## Scope

- `src/awsquery/default_filters.yaml` — audit, fix `Tags$` and any other `$`-anchored entries that miss flattened keys
- `src/awsquery/config.py` — extend `apply_default_filters` to support additive merge
- `src/awsquery/cli.py` — recognise `+`-prefixed column args and pass an "additive" flag through
- `src/awsquery/filters.py` (or wherever column args are tokenised) — strip `+` prefix and tag the column as additive
- `tests/unit/test_default_column_filters.py` and friends — coverage for both fixes
- `README.md` — document the new `+Column` prefix

## Acceptance Criteria

- [ ] Walk every `$`-suffix entry in `default_filters.yaml`; classify and fix all that anchor against post-transformation-invisible keys
- [ ] `awsquery ec2 describe-instances` and `awsquery ec2 describe-vpcs` show the `Name` tag populated by default (concrete proof in test or screenshot)
- [ ] `+Column` CLI syntax merges with defaults (dedup + order-preserving); bare `Column` still replaces defaults
- [ ] Multiple `+`-prefixed columns work in the same invocation
- [ ] Unit + integration tests cover both the corrected defaults and the additive-merge logic
- [ ] Research phase uses graphify (per request) and the resulting RESEARCH.md notes whether it was actually useful for tracing call sites (filter parsing → default application → output formatting)
- [ ] README's filter section documents `+Column`
- [ ] Post-fix audit pass confirms no regressions and no remaining broken `$`-suffix defaults

## Notes for Research

The user explicitly asked that graphify be used in research and that its usefulness be evaluated. The graph isn't built yet — research will need to run `graphify update /workspace` (free, AST-only) or the issue-pipeline `ensure-graphs` helper. Capture in RESEARCH.md whether call-graph queries (e.g. "who calls `apply_default_filters`", "who calls `transform_tags_structure`", "what depends on `parse_filter_pattern`") materially helped vs `grep`+`Read`.
