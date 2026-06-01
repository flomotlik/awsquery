# Ecosystem research — sue5t

## Scope check

This issue is **entirely internal** to awsquery — no new third-party deps required. Both fixes use machinery already shipped:

- The Tags fix touches a YAML config file (`default_filters.yaml`) and reuses `ShapeCache` + `transform_tags_structure` (already in `formatters.py`/`shapes.py`).
- The `+Column` syntax is pure Python argument parsing on top of the existing `argparse` setup; no new CLI library is justified.

The CONTEXT.md D7 explicitly excludes restructuring `default_filters.yaml` and adding alternative flags like `--additive`. The locked decisions narrow the design space hard enough that ecosystem research is mostly about confirming "don't reach for anything new."

## Existing stack — already pinned in `pyproject.toml`

| Library    | Version (pyproject.toml) | Purpose                                    | Touched by this issue |
|------------|--------------------------|--------------------------------------------|-----------------------|
| `boto3`    | >=1.34.0                 | AWS API client; service model introspection | Indirect (via `ShapeCache`) |
| `botocore` | (transitive)             | Service model loader                       | Indirect (via `ShapeCache.get_service_model`) |
| `argcomplete` | >=2.0.0               | Shell completion                           | No change             |
| `tabulate` | >=0.9.0                  | Table output                               | No change             |
| `PyYAML`   | >=6.0                    | `default_filters.yaml` loader              | No change (config edits only) |
| `pytest`   | >=7.0                    | Test runner                                | Test additions        |

## Standard stack

| Decision area                            | Approach                                                       | Why                                                                          | Confidence |
|------------------------------------------|----------------------------------------------------------------|------------------------------------------------------------------------------|------------|
| `+` detection                            | `str.startswith('+')` after `sanitize_input`                   | Trivial; no parser needed.                                                   | HIGH       |
| `+`-strip location                       | Inside `cli.py::determine_column_filters` (or a small helper)  | See codebase.md — keeps grammar layer untouched, validator gets clean input. | HIGH       |
| Merge function                           | `dict.fromkeys(merged_list).keys()` for ordered dedup          | Stdlib, O(n), preserves first-seen order. CPython 3.7+ ordered-dict semantics are stable. Project requires Python 3.10+ (pyproject.toml). | HIGH       |
| Audit driver                             | New script `scripts/audit_default_filters.py` (prototype in codebase.md) | Project already has `scripts/validate-awsquery.sh`; matches convention.       | HIGH       |
| YAML emission for fixes                  | Edit `default_filters.yaml` by hand (5-6 lines)                | Tiny diff; mechanical edits don't justify a generator.                       | HIGH       |
| Test framework for additive logic        | pytest with `parametrize` (the only allowed marker)            | Matches existing test style; CLAUDE.md mandates no other markers.            | HIGH       |

## Don't hand-roll

| Problem                                | Don't build                                       | Use instead                                                                                                 | Why                                                                                                 |
|----------------------------------------|---------------------------------------------------|-------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Shape introspection                    | New AST/regex parser over `default_filters.yaml`  | Existing `ShapeCache.get_response_fields()`                                                                  | It's already shape-aware AND case-insensitive matches runtime. Audit just wraps it.                |
| Tag transform simulation               | A second copy of `transform_tags_structure`       | Apply the same K/V detection inline in the audit (see codebase.md prototype)                                | Avoid drift between audit and runtime. The K/V detection is just 5 lines.                          |
| `+` argument parser                    | argparse `type=` callback or custom action        | `str.startswith('+')` partition in `determine_column_filters`                                               | argparse does not see column-filter args as named params — they're remainder positionals.          |
| Default-filter order-preserving merge  | Custom `OrderedDict` dance                        | `list(dict.fromkeys(defaults + user_columns_stripped))`                                                     | Idiom is stable since Python 3.7; project requires 3.10+.                                          |
| YAML diff verification                 | Snapshot the entire file                          | Targeted assertions on just the changed service+action keys                                                 | Smaller, more maintainable diff in the test.                                                       |

## Architecture patterns

### Recommended approach

1. **Audit script first** (`scripts/audit_default_filters.py`). Run it pre-fix to capture the baseline, again post-fix to assert "broken count ≤ baseline minus targeted fixes". Don't gate CI on absolute zero — the heuristic has known false positives (see codebase.md). Use it as a regression detector.

2. **Targeted YAML edits.** Five concrete entries (from codebase.md per-service table). Plus the leftover `redshift describe_cluster_parameter_groups Key$/Value$` cleanup.

3. **`+`-prefix handling concentrated in `determine_column_filters`.** Two new helpers:
   - `_partition_additive(cols: list[str]) -> tuple[bool, list[str]]` — returns `(additive_mode, stripped_user_cols)`.
   - `_merge_with_defaults(defaults: list[str], user: list[str]) -> list[str]` — order-preserving dedup, defaults first.

4. **Extend `apply_default_filters(service, action, user_columns=None, additive=False)`.** When `additive=True`, return `_merge_with_defaults(get_default_columns(service, action), user_columns)`. When `additive=False` and `user_columns` non-empty, return `user_columns` (today's behavior).

5. **stderr messaging.** Today: `Using default columns: -- A B C`. In additive mode: `Using default columns + user additions: -- A B C +D` (or similar). The user's existing copy-pasteable hint format (`_format_columns_copyable`) should be reused.

### Anti-patterns to avoid

- **Don't change `parse_filter_pattern`.** `+` lives at CLI-args level; the pattern grammar is for `^…$` only (CONTEXT.md D7 explicit).
- **Don't introduce `--additive` flag.** CONTEXT.md D7 defers it.
- **Don't strip `+` inside `parse_multi_level_filters_for_mode`.** That function is shared between single/multi modes and doesn't know about column-vs-value semantics until after segment splitting. Strip later, in `determine_column_filters`.
- **Don't skip `FilterValidator` for additive entries.** Validator runs on the merged list (post-strip). The Tag short-circuit (`filter_validator.py:85`) makes most Tag-related additions auto-pass.
- **Don't bake the audit list into the YAML as comments.** The YAML is the source of truth; the audit script (re-runnable) is the verification.

## Alternatives considered

| Instead of            | Could use                                       | Tradeoff                                                                                                                              |
|-----------------------|-------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `+Foo` prefix         | `--additive` CLI flag + bare columns merge      | More verbose; users have to remember a flag. CONTEXT.md D1 picks the prefix; D7 defers the flag.                                       |
| `+Foo` prefix         | `--add-column Foo` repeated                     | Even more verbose; conflicts with `argparse.append` action which would steal the syntax. CONTEXT.md D1 locks the prefix.                |
| Per-service `Tags$` replacement | Global `Tags$ → Tags.Name$` rewrite          | Breaks string-list-tagged services (ecr `imageTags`). CONTEXT.md D4 mandates per-service classification.                                |
| Audit script in Python | Awk/sed over the YAML                          | Won't model the K/V transform. Audit MUST use `ShapeCache` to be correct.                                                              |
| Bake audit into CI as a hard gate | Run as advisory pre-merge check        | Heuristic has false positives (`value$`, list-of-primitive top-level data fields). Gate would block legitimate config.                  |

## Library docs touched (Context7 not needed)

This issue uses zero new external libraries. The Python 3.10+ `dict.fromkeys` ordered semantics (the merge-dedup primitive) is a long-stable language feature — no doc lookup required.

## Sources

### HIGH confidence
- Live verification of `parse_filter_pattern`, `matches_pattern`, `_process_remaining_args`, argparse `+` handling (see codebase.md)
- Direct inspection of `src/awsquery/{config,cli,filters,formatters,shapes,filter_validator,auto_filters}.py`
- `tests/unit/test_default_column_filters.py`, `tests/unit/test_filter_implementation.py`
- `default_filters.yaml` audit prototype (1,961 entries audited)
- `pyproject.toml` deps (already on disk)

### MEDIUM confidence
- (none — every claim is locally verifiable)

### LOW confidence
- (none — nothing required web search)
