---
slug: sue5t-fix-tags-default-filters-and-add-additive-column-syntax
stage: discuss
generated: 2026-06-01
---

# Design decisions — sue5t

Captured before research/plan. The issue itself (`ISSUE.md`) describes the *what*; this file pins down the *how* on the points where reasonable people would diverge.

## D1 — `+Column` semantics: global mode flip

**Decision:** the presence of any `+`-prefixed argument *anywhere* in the column-filter group switches the whole invocation into additive mode. The defaults from `default_filters.yaml` are kept, and ALL named columns (bare and `+`-prefixed alike) merge with them.

Truth table:

| User columns          | Resulting columns                          |
| :-------------------- | :----------------------------------------- |
| (none)                | defaults                                   |
| `Foo Bar`             | `[Foo, Bar]` — replaces defaults (today)   |
| `+Foo`                | `defaults + [Foo]`                         |
| `Foo +Bar`            | `defaults + [Foo, Bar]`                    |
| `+Foo +Bar`           | `defaults + [Foo, Bar]`                    |

**Why this and not the alternatives:** keeps the today behavior of bare-only ("just give me these columns, no defaults") *and* gives the user a one-character escape hatch to opt in to defaults. The alternative "per-column" form leaves "bare + `+`" mixed mode ambiguous, and "strict split (error if mixed)" forces users to either fully type out the defaults or fully use `+`.

## D2 — Merge order and dedup

**Decision:** defaults first (in `default_filters.yaml` order), then user-added columns in CLI argument order. Dedup is case-sensitive (matches today's filter-matching semantics), exact-string on the full pattern. If a user-added pattern equals a default pattern verbatim, it appears once at the default's position.

Open: if a user adds `+Tags.Name` and a default is `Tags.Name`, we keep one. If a user adds `+^Tags\.` and defaults have `Tags.Name`, the patterns are semantically overlapping but textually different — we keep both. Living with this for now; the worst case is a redundant column, which the column-width fitter handles gracefully.

## D3 — Scope of `+` within the multi-level filter syntax

**Decision:** `+` applies *only* to the column-filter group (the pre-`--` arguments or whatever filter mode `parse_multi_level_filters_for_mode` classifies as column filters). Value filters and resource filters keep their existing semantics — they don't have "defaults" to merge with.

## D4 — `Tags$` replacement: per-service, not uniform

**Decision:** the audit picks the right replacement per service. Concretely:

- **Key/value-tagged services (ec2, rds, elasticache, eks, lambda, …):** replace `Tags$` with `Tags.Name`. After `transform_tags_structure`, `Tags.Name` is the standard human-readable identifier.
- **String-list-tagged services (ecr `imageTags`, possibly others):** replace `imageTags$` with bare `imageTags` (substring/contains match). The flattened form is `imageTags.0`, `imageTags.1`, etc.; substring match captures all of them.
- **Anything else surfacing in the audit:** decide case-by-case based on the actual shape.

Research must produce a per-service classification before plan finalises the YAML edits.

## D5 — Audit criterion: static + shape-aware

**Decision:** a `Foo$` entry is **broken** if, for the service+operation it's attached to, `Foo` does not appear as a *post-transform* field name in the response shape.

Concretely: walk every `$`-anchored entry, look up its service+operation shape via `ShapeCache`, simulate the same flattening the formatter would apply (`flatten_dict_keys` + `transform_tags_structure`), and check whether any resulting key ends with `Foo`. If none do, the entry is broken.

- `Id$` is fine — flattened keys like `InstanceId`, `VpcId` end with `Id`.
- `Tags$` is broken — after `transform_tags_structure`, no key ends with literal `Tags`; the keys are `Tags.Name`, `Tags.Environment`, etc.
- Typos surface for free (e.g. `Tagss$` matches nothing).

Out of scope: validating that the *match* is *useful* (e.g. `Id$` matches both `OwnerId` and `InstanceId` — only the latter is interesting). The issue is correctness of anchoring, not column-selection quality.

## D6 — Graphify: pre-build now, research uses it

**Decision:** before spawning the researcher, run `graphify update /workspace` once to seed `/workspace/graphify-out/graph.json`. The researcher then receives the graph through the issue pipeline's `ensure-graphs` helper (which produces `.worktrees/.mcp/<slug>.json`). AST-only, free, no LLM cost.

Research must capture in RESEARCH.md whether call-graph queries actually paid off vs `grep`+`Read` for this issue's specific questions:

- "Who calls `apply_default_filters`?" — likely `cli.py` only, but worth confirming
- "Who calls `transform_tags_structure`?" — affects D5 (the flattening path)
- "What are the callees of `parse_multi_level_filters_for_mode`?" — affects D3 (where `+` parsing slots in)
- "What depends on `parse_filter_pattern`?" — affects D1/D5 (anchoring semantics)

If graphify materially shortened any of these, that's a data point for #68 (Graphify integration parent issue). If not, RESEARCH.md should say so plainly.

## D7 — Out of scope (deliberately)

- `-Column` subtractive syntax — interesting but separate concern; not asked.
- Multi-character "modes" like `++Col` (force-add) — over-engineered.
- Re-organising the structure of `default_filters.yaml` — fix entries in place.
- Changing the filter grammar (`^...$`, contains, prefix, suffix) — `+` lives in CLI arg parsing, not in `parse_filter_pattern`. The grammar stays.

## Open questions (defer to plan)

- Exact module placement for `+`-prefix stripping: in `cli.py` argument processing, or in `filters.py` alongside the existing pattern parsing? Lean toward `cli.py` because `+` is about *args*, not patterns — but research should map the data flow first.
- Whether to expose an `--additive` flag as a non-prefix alternative (e.g. for users on shells that special-case `+`). Defer until research shows whether any shell actually breaks here.
- Test fixture strategy for the audit: snapshot the corrected `default_filters.yaml`, or write unit tests that exercise the audit function itself against synthetic shape models. Both are reasonable.
