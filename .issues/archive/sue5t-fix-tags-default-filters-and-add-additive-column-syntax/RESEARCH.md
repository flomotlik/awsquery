# Research: Fix Tags$ default filters and add additive +Column syntax

**Researched:** 2026-06-01
**Issue:** sue5t-fix-tags-default-filters-and-add-additive-column-syntax
**Confidence:** HIGH (all claims verified against the worktree's actual code and live shape introspection)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D1 — `+Column` semantics: global mode flip.** Presence of any `+`-prefixed argument anywhere in the column-filter group switches the whole invocation into additive mode. Defaults from `default_filters.yaml` are kept, and ALL named columns (bare and `+`-prefixed alike) merge with them.

| User columns          | Resulting columns                          |
| :-------------------- | :----------------------------------------- |
| (none)                | defaults                                   |
| `Foo Bar`             | `[Foo, Bar]` — replaces defaults (today)   |
| `+Foo`                | `defaults + [Foo]`                         |
| `Foo +Bar`            | `defaults + [Foo, Bar]`                    |
| `+Foo +Bar`           | `defaults + [Foo, Bar]`                    |

**D2 — Merge order and dedup.** Defaults first (in `default_filters.yaml` order), then user-added columns in CLI argument order. Dedup is case-sensitive, exact-string on the full pattern. Living with redundant columns when patterns are semantically overlapping but textually different.

**D3 — Scope of `+`.** Applies only to the column-filter group. Value filters and resource filters keep their existing semantics.

**D4 — `Tags$` replacement: per-service.**
- Key/value-tagged services (ec2, rds, elasticache, eks, lambda, …): replace `Tags$` with `Tags.Name$` (or per-service equivalent).
- String-list-tagged services (ecr `imageTags`, …): replace with bare substring/contains match.
- Anything else surfacing in the audit: decide case-by-case based on the actual shape.

**D5 — Audit criterion: static + shape-aware.** A `Foo$` entry is broken if, for the service+operation it's attached to, `Foo` does not appear as a *post-transform* field name in the response shape. Concrete process: walk every `$`-anchored entry, look up its service+operation shape via `ShapeCache`, simulate the same flattening the formatter would apply (`flatten_dict_keys` + `transform_tags_structure`), and check whether any resulting key ends with `Foo` (case-insensitive, matching runtime semantics).

**D6 — Graphify pre-built; research uses it AND evaluates it.** Graph at `/workspace/graphify-out/graph.json` (3,616 nodes, 5,217 edges). Capture in RESEARCH.md whether call-graph queries actually paid off. See [Graphify usefulness](#graphify-usefulness) below — verdict: **worth integrating; the JSON `links` traversal pattern is faster than grep for trace questions; the CLI `query` is keyword-BFS and noisy**.

### Claude's Discretion

- Module placement for `+`-prefix stripping: research **strongly recommends `cli.py::determine_column_filters`** as the strip site (verified — see Data Flow section below).
- Audit fixture strategy: research recommends **a re-runnable audit script** at `scripts/audit_default_filters.py` (prototype below), not a snapshot. Snapshots drift quickly when boto3 ships new service shapes.
- Whether to expose `--additive` flag: defer per D7. No shell breaks `+` per live testing (zsh/bash treat `+` as literal).

### Deferred Ideas (OUT OF SCOPE)

- `-Column` subtractive syntax
- Multi-character mode prefixes (`++Col`)
- Restructuring `default_filters.yaml`
- Changing the filter grammar (`^…$`)
- Fixing `ssm.get_parameters Parameters$` (separate audit finding, unrelated to Tags or additive) — defer to a follow-up issue.

</user_constraints>

## Project Constraints (from CLAUDE.md)

Captured from `/workspace/.worktrees/sue5t-…/CLAUDE.md`. The planner MUST comply.

- **ZERO backward compatibility.** Internal APIs (e.g. `apply_default_filters` signature) are free to change. CLI surface is the only stability boundary.
- **MANDATORY specialized agents.**
  - All test work → `@agent-test-writer`
  - All Python implementation → `@agent-python-infra-automator`
  - Post-change code review → `@agent-code-reviewer` (automatic)
  - Any Makefile work → `@agent-makefile-optimizer`
- **NO pytest markers** (except `@pytest.mark.parametrize`). Discovery is directory-based (`tests/unit/`, `tests/integration/`).
- **NO verbose test docstrings.** No TDD placeholders, no "Test the X function" docstrings, no implementation re-statements. Code is self-documenting.
- **Single-line commit messages**, ≤72 chars, with the standard trailer. No bullets, no multi-paragraph bodies.
- **No duplicate test files.** Filter tests → `test_filter_implementation.py`. Default-column tests → `test_default_column_filters.py`. CLI flag tests → `test_cli_flags.py`. Reuse existing files.
- **Test real implementation, not mocks.** Mock only external dependencies (boto3, file I/O).
- **Tests must cover edge cases** including malformed input, Unicode, empty values.

## Summary

The issue is in two parts and both are tractable with the existing machinery.

**Part 1 (broken `Tags$` defaults).** After auditing all 1,961 `$`-suffix entries in `default_filters.yaml` against live `ShapeCache` introspection + a simulated `transform_tags_structure` + `flatten_dict_keys` pass, only **5 entries are truly broken in the Tags class** the issue cares about (`directconnect tags$`, `ec2 describe_vpcs Tags$`, `redshift describe_cluster_parameter_groups Tags$`, `redshift describe_cluster_security_groups Tags$`, `ecr describe_images imageTags$`). Two extra leftovers (`redshift describe_cluster_parameter_groups Key$` and `Value$`) should be deleted as part of this fix. Note: `directconnect` requires a small companion fix to `_is_aws_tags_structure` because the service shape uses lowercase `key`/`value` and the current transform is case-sensitive.

**Part 2 (additive `+Column`).** Live verification shows `+Foo` has NO existing grammar meaning, argparse passes it through cleanly, all CLI helper paths preserve it, and `parse_multi_level_filters_for_mode` routes it to the column-filter group untouched. The cleanest integration point is at the top of `cli.py::determine_column_filters` — partition into `additive_present` and `stripped_user_cols`, then extend `apply_default_filters` to accept `additive=True` and return `list(dict.fromkeys(defaults + stripped_user_cols))` for order-preserving dedup.

**Primary recommendation:** Implement Part 2 first (additive `+Column`) — it's a tightly scoped, low-risk addition with clear test coverage. Then Part 1 (Tags audit + fixes) — ship a re-runnable `scripts/audit_default_filters.py`, apply the 5 targeted YAML edits + 2 leftover deletions, and patch `_is_aws_tags_structure` to accept case-variant `Key`/`Value`. Test with `@agent-test-writer`, implement with `@agent-python-infra-automator`, review with `@agent-code-reviewer`.

## Codebase Analysis

### Relevant Code

| File                                                | Purpose                                                                | Last Modified | Relevance |
|-----------------------------------------------------|------------------------------------------------------------------------|---------------|-----------|
| `src/awsquery/config.py`                            | `load_default_filters`, `get_default_columns`, `apply_default_filters` (THE merge point) | stable        | CRITICAL  |
| `src/awsquery/cli.py`                               | `main()`, `determine_column_filters` (the `+`-strip site)              | stable        | CRITICAL  |
| `src/awsquery/filters.py`                           | `parse_filter_pattern`, `matches_pattern`, `parse_multi_level_filters_for_mode` (passes `+Foo` through) | stable | HIGH    |
| `src/awsquery/formatters.py`                        | `transform_tags_structure` (case-sensitive `Key`/`Value`!), `flatten_dict_keys`, `filter_columns` | stable | HIGH    |
| `src/awsquery/shapes.py`                            | `ShapeCache` — audit reuses this                                       | stable        | HIGH      |
| `src/awsquery/filter_validator.py`                  | Validates merged column list; short-circuits on `"tag" in filter.lower()` | stable     | MEDIUM    |
| `src/awsquery/default_filters.yaml`                 | 1,961 `$`-suffix entries; 5 broken in Tags class + 2 leftovers         | stable        | CRITICAL  |
| `tests/unit/test_default_column_filters.py`         | Existing test home for defaults + apply_default_filters logic           | stable        | HIGH      |
| `tests/unit/test_filter_implementation.py`          | Filter pattern + matching tests                                        | stable        | MEDIUM    |
| `tests/unit/test_tags_transformation.py`            | Tag transform tests — add lowercase fixture for directconnect          | stable        | MEDIUM    |

### Data flow (verified via graphify + live tracing)

```
main()  ← cli.py:639
  ↓ parse_known_args (first pass), then _process_remaining_args(...) to reorder flags
  ↓ filter_argv = _build_filter_argv(args, remaining)
  ↓ _, resource_filters, value_filters, column_filters = parse_multi_level_filters_for_mode(filter_argv, mode="single")
  ↓ column_filters = [sanitize_input(f) for f in column_filters]           # cli.py:810
  ↓ final_column_filters = determine_column_filters(column_filters, service, action, json_output=args.json)   # cli.py:962
        ┌── ★ +Column STRIP SITE ★ — partition into (additive_present, bare_cols, +-stripped_user_cols)
        │   if additive_present:
        │       merged = list(dict.fromkeys(get_default_columns(service, action) + stripped_user_cols))
        │       column_filters_to_use = merged
        │   elif column_filters:                              # bare-only (today's replace-defaults branch)
        │       column_filters_to_use = column_filters
        │   else:                                             # no user cols → defaults / auto-select
        │       ...
        └── FilterValidator().validate_columns(service, action, column_filters_to_use)   # cli.py:384
  ↓ output = format_table_output(filtered_resources, final_column_filters)
        → filter_columns → parse_filter_pattern + matches_pattern (case-insensitive)
```

**Strip site rationale:** `parse_filter_pattern` is grammar-level (`^…$`); `+` is a CLI-level mode flip; CONTEXT.md D7 forbids touching the grammar. The validator must receive `+`-stripped patterns (it doesn't know about `+`). `determine_column_filters` is the single funnel between user input and validator+default-merge → the unique correct strip location.

### Interfaces

<interfaces>
// From src/awsquery/config.py — TODAY's signature
def load_default_filters() -> dict
def get_default_columns(service: str, action: str) -> list[str]
def apply_default_filters(service: str, action: str, user_columns: list[str] | None = None) -> list[str] | None
    # TODAY: returns user_columns directly if any are provided; else loads defaults; else None.
    # CHANGE (CLAUDE.md ZERO backwards compat permits): extend to additive.
    #   def apply_default_filters(service, action, user_columns=None, additive=False) -> list[str] | None
    #   When additive=True and user_columns non-empty:
    #     defaults = get_default_columns(service, action) or []
    #     merged = list(dict.fromkeys(defaults + user_columns))   # dedup preserves first-seen order
    #     return merged if merged else None
    #   When additive=False (today's path): unchanged.

// From src/awsquery/cli.py — the integration site
def determine_column_filters(
    column_filters: list[str] | None,
    service: str,
    action: str,
    json_output: bool = False
) -> list[str] | None
    # ADD at the top:
    #   additive_present = any(c.startswith('+') for c in (column_filters or []))
    #   if additive_present:
    #       user_cols = [c[1:] if c.startswith('+') else c for c in column_filters]
    #       defaults = apply_default_filters(service, action, user_columns=user_cols, additive=True)
    #       column_filters_to_use = defaults or user_cols
    #       # stderr echo: f"Using default columns + additions: {_format_columns_copyable(column_filters_to_use)}"
    #       # then skip the bare-only branch and go to FilterValidator
    #   else:  (existing logic unchanged)

# Surrounding helpers (referenced; unchanged)
def _process_remaining_args(remaining: list[str]) -> tuple[list[str], list[str]]
def _process_remaining_args_after_separator(remaining: list[str]) -> tuple[list[str], list[str]]
def _build_filter_argv(args, remaining: list[str]) -> list[str]
def _format_columns_copyable(columns: list[str]) -> str
    # Recommendation: extend to render '+' prefixes when displaying additive mode columns to stderr,
    # so the echoed command is copy-paste-runnable.

// From src/awsquery/filters.py — UNCHANGED by this issue
def parse_filter_pattern(filter_text: str) -> tuple[str, str]
    # Live-verified: '+Foo' → ('+Foo', 'contains'); '+Foo$' → ('+Foo', 'suffix').
    # '+' has NO grammar meaning. Repurposing at CLI level has zero collision.
def matches_pattern(text, pattern, mode) -> bool
    # CASE-INSENSITIVE (both sides lowercased).
def filter_resources(resources, value_filters) -> list[dict]
def parse_multi_level_filters_for_mode(argv, mode="single") -> tuple[list, list, list, list]
    # Returns (base_command, resource_filters, value_filters, column_filters).
    # Live-verified: '+Foo' tokens preserved into the column_filters list unchanged.

// From src/awsquery/formatters.py
def transform_tags_structure(data, max_depth=10, current_depth=0)
    # Rewrites {Tags: [{Key,Value}, ...]} → {Tags: {Key: Value, ...}} recursively.
    # *** ALERT *** _is_aws_tags_structure requires CASE-SENSITIVE 'Key' and 'Value' member names.
    # directconnect uses lowercase 'key'/'value' → transform does NOT fire there → Tags.Name fix
    # alone is insufficient. Companion fix needed (see Pitfalls P1).
def _is_aws_tags_structure(value) -> bool                                       # ← case-sensitive bug
def _transform_aws_tags_list(tags_list) -> dict                                 # ← also case-sensitive
def flatten_dict_keys(d, parent_key="", sep=".") -> dict
    # Lists-of-dict → "<parent>.<i>.<child>"; lists-of-primitive → "<parent>.<i>"; non-dict d → {"value": d}.
def filter_columns(flattened_data, column_filters) -> dict
def format_table_output(resources, column_filters=None, max_width=None) -> str
def format_json_output(resources, column_filters=None) -> str

// From src/awsquery/shapes.py — REUSE for audit
class ShapeCache:
    def get_response_fields(self, service: str, operation: str) -> tuple[str|None, dict[str,str], dict[str,str]]
        # Returns (data_field, simplified_fields, full_fields).
        # Audit uses simplified_fields. Adds {'value': 'list'} pseudo-field when top-level data field is list-of-primitive.

// From src/awsquery/filter_validator.py — IMPORTANT short-circuits
class FilterValidator:
    def validate_columns(self, service, operation, column_filters: list[str]) -> list[tuple[str, str|None]]
        # CRITICAL: short-circuits for 'tag' in filter.lower() (line 85). Tag-related patterns always pass.
        # Also short-circuits for map-wildcard shapes (sns/sqs get-*-attributes).
        # Receives `+`-STRIPPED patterns. The strip happens upstream in determine_column_filters.

// Audit-related (new file proposed by planner)
// scripts/audit_default_filters.py — see codebase.md for the 90-LOC prototype
def audit_default_filters(config_path='src/awsquery/default_filters.yaml') -> dict
    # Returns {'broken': [...], 'correct': [...], 'wildcard': [...], 'kv_dyn': [...], 'unverified': [...]}.
    # Heuristic — manual review of 'broken' is required (known false-positives on `value$` for top-level
    # list-of-primitive data fields).
</interfaces>

### Reusable components

- `ShapeCache.get_response_fields()` — no extension required for the audit.
- `_format_columns_copyable()` in cli.py — extend slightly for additive mode messaging.
- `transform_tags_structure` + `flatten_dict_keys` — used as-is at runtime; the audit simulates them.
- Existing test fixtures in `tests/unit/test_default_column_filters.py`: keep the layout (TestApply…, TestDetermine…), add new test classes.

### Potential conflicts

- **`_is_aws_tags_structure` case sensitivity** vs lowercase-tag services (directconnect). Sub-fix needed (P1).
- **`apply_default_filters` signature change** — all existing tests in `test_default_column_filters.py` that call `apply_default_filters("ec2", "describe_instances", user_columns)` must continue to compile under the new `additive=False` default. Confirmed they do (positional + keyword default fully back-compatible at call-site, even though CLAUDE.md says we don't owe back-compat).
- **`FilterValidator`** receives the merged column list — if any merged entry isn't tag-related and doesn't match the shape, the validator prints a warning. Add tests asserting NO warnings fire for the canonical additive cases.

### Code patterns in use

- **Cached YAML config** via `@lru_cache(maxsize=1)` on `load_default_filters` — keep.
- **Case-insensitive matching at runtime, case-sensitive at config** — audit honors this.
- **Heuristic + manual-review pattern** for any new "broken" detection (per CLAUDE.md philosophy of "test real impl, not mocks").
- **Single-arg-position parsing in cli.py** — `+Foo` is a positional that flows through `_process_remaining_args` and `_build_filter_argv` cleanly.

## Standard Stack

| Library    | Version (pinned in pyproject.toml) | Purpose                              | Why Standard                       | Confidence |
|------------|-----|------|------|------|
| `boto3`    | >=1.34.0 (live 1.43.18)            | Shape introspection for audit        | Already a hard dep; ShapeCache wraps it | HIGH       |
| `PyYAML`   | >=6.0                              | Config loader                        | Already used by `config.py`        | HIGH       |
| `argcomplete` | >=2.0.0                          | CLI completion                       | No change                          | HIGH       |
| `pytest`   | >=7.0                              | Test runner                          | Existing convention                | HIGH       |
| `tabulate` | >=0.9.0 (live 0.10.0)              | Output                               | No change                          | HIGH       |

### Alternatives considered

| Instead of                          | Could use                          | Tradeoff                                                                                  |
|-------------------------------------|------------------------------------|-------------------------------------------------------------------------------------------|
| `+Column` prefix                    | `--additive` flag                  | CONTEXT.md D1 picks the prefix; D7 defers the flag                                         |
| `+`-strip in `determine_column_filters` | `+`-strip in `parse_filter_pattern` | Would leak CLI semantics into grammar layer; CONTEXT.md D7 forbids                         |
| Re-runnable audit script             | Snapshot of corrected YAML        | Snapshot drifts when boto3 ships new shapes; script is self-updating                       |
| Heuristic-only audit                 | Full per-operation manual review  | 1,861 entries — script narrows to ~33 candidates + manual review of 5-7 actual broken     |
| `set()` dedup                       | `dict.fromkeys()` dedup            | `set` doesn't guarantee order; project is 3.10+ so `dict.fromkeys` is safe                |

## Don't Hand-Roll

| Problem                                | Don't build                                       | Use instead                                                       | Why                                                                  |
|----------------------------------------|---------------------------------------------------|-------------------------------------------------------------------|----------------------------------------------------------------------|
| Shape introspection                    | New AST parser over YAML                          | Existing `ShapeCache.get_response_fields()`                       | Already shape-aware, matches runtime semantics                       |
| Tag-transform simulation               | A copy of `transform_tags_structure`              | Inline K/V detection in audit (5 lines)                           | Avoid drift between audit and runtime                                |
| `+`-prefix CLI parser                  | argparse `type=` callback or custom action        | `str.startswith('+')` partition in `determine_column_filters`     | argparse doesn't see column-filter args as named params              |
| Order-preserving dedup                 | Custom `OrderedDict` dance                        | `list(dict.fromkeys(defaults + stripped))`                        | Stable since Python 3.7; project requires 3.10+                      |
| Audit CI integration                   | Hard-gate broken-count to zero                    | Advisory pre-merge report (heuristic has known false-positives)   | Better signal-to-noise; script flags candidates, humans decide       |

## Architecture Patterns

### Recommended approach (sequenced)

**Phase A — `+Column` additive syntax** (lower risk, simpler tests):

1. Extend `apply_default_filters(service, action, user_columns=None, additive=False)` — add the `additive` keyword arg; when truthy AND `user_columns` non-empty, return `list(dict.fromkeys(get_default_columns(...) + user_columns))`.
2. In `cli.py::determine_column_filters`, add a guard at the very top: if any `c.startswith('+')` in `column_filters`, set `additive_present=True`, strip the leading `+` from any entry that has one, and route to the new `additive=True` branch.
3. Update stderr echo (`_format_columns_copyable`) to render the merged list in copy-paste form.
4. Tests:
   - `tests/unit/test_default_column_filters.py` — new classes `TestApplyDefaultFiltersAdditive`, `TestDetermineColumnFiltersAdditive`.
   - `tests/unit/test_cli_flags.py` OR `test_cli_parser.py` — verify `+Foo` doesn't break argument parsing (paranoia regression).
   - All via `@agent-test-writer`.

**Phase B — `Tags$` audit + fixes** (heavier, requires manual review):

1. Add `scripts/audit_default_filters.py` (prototype in codebase.md). Reports broken/correct/kv-dyn/wildcard/unverified counts. Pretty-prints broken entries with reason.
2. Run audit, manually review the ~33 candidates, identify the 5-7 actually broken in scope.
3. Edit `default_filters.yaml`:
   - `directconnect.describe_direct_connect_gateways`: `tags$` → `tags.Name` (substring) — AFTER P1 fix to `_is_aws_tags_structure`.
   - `ec2.describe_vpcs`: `Tags$` → `Tags.Name$`
   - `redshift.describe_cluster_parameter_groups`: `Tags$` → `Tags.Name$`; delete `Key$`, `Value$`.
   - `redshift.describe_cluster_security_groups`: `Tags$` → `Tags.Name$`
   - `ecr.describe_images`: `imageTags$` → `imageTags` (substring, no `$`)
4. Patch `_is_aws_tags_structure` and `_transform_aws_tags_list` in `formatters.py` to accept case-variant `Key`/`Value` member names.
5. Add `tests/unit/test_tags_transformation.py` cases for lowercase fixtures.
6. README update — document `+Column` syntax.

**Phase C — End-to-end validation:**

1. Run audit before/after; diff must show only the targeted reductions in broken count.
2. Run full test suite (`make test`) — directory-based, no markers (CLAUDE.md).
3. `@agent-code-reviewer` post-merge review.

### Anti-patterns to avoid

- **Don't change `parse_filter_pattern`** — grammar must stay.
- **Don't introduce `--additive` CLI flag** — deferred by D7.
- **Don't strip `+` inside `parse_multi_level_filters_for_mode`** — wrong layer; affects both single/multi modes uniformly when `+` should only apply to columns (D3).
- **Don't gate CI on audit "zero broken"** — heuristic has documented false positives.
- **Don't bake `Tags$` → `Tags.Name$` as a global YAML rewrite** — breaks string-list-tagged services (CONTEXT.md D4).
- **Don't skip running `@agent-test-writer` / `@agent-python-infra-automator`** — CLAUDE.md mandates them.

## Common Pitfalls

### P1 — directconnect uses lowercase `key`/`value`; `transform_tags_structure` won't fire
**What goes wrong:** Replacing `tags$` with `tags.Name` won't surface Name post-transform because the transform's `_is_aws_tags_structure` (formatters.py:195) requires literal `"Key"`/`"Value"` member names.
**Why:** Botocore's directconnect shape uses lowercase member names; `_is_aws_tags_structure` is case-sensitive.
**How to avoid:** Patch `_is_aws_tags_structure` and `_transform_aws_tags_list` to handle case-variant `Key`/`Value`. Add a unit-test fixture with lowercase-key tags.
**Warning signs:** `awsquery directconnect describe-direct-connect-gateways` shows empty Name. (Should also be an integration check before merge.)

### P2 — `FilterValidator` warns on `+Foo` if the strip happens late
**What goes wrong:** Validator receives raw `+InstanceId`, doesn't short-circuit on it, prints "matches no fields" warning.
**Why:** `_validate_single_column` only short-circuits on `"tag" in filter.lower()` and map-wildcard shapes.
**How to avoid:** Strip `+` BEFORE calling `FilterValidator.validate_columns`. The natural location is the top of `determine_column_filters`.
**Warning signs:** stderr warnings appearing for every additive run. Test: `awsquery ec2 describe-instances +InstanceId` must produce clean stderr (no validation warning).

### P3 — Order-preserving dedup with `set()` silently scrambles order
**What goes wrong:** Tests pass on CPython by accident, fail on PyPy.
**How to avoid:** Use `list(dict.fromkeys(...))`. Project is 3.10+; dict order is language-spec.
**Warning signs:** flaky column-order tests.

### P4 — Case-sensitive dedup keeps near-duplicates that are runtime-equivalent
**What goes wrong:** `+InstanceId` + default `instanceid$` → two entries; both match at runtime; double column in output.
**Why:** Dedup operates on raw string; runtime matching is case-insensitive.
**How to avoid:** Per CONTEXT.md D2, accept the redundancy. Don't promote to case-insensitive dedup (out of scope).

### P5 — `Tags.Name$` matches nested `EncryptionControl.Tags.Name` in `ec2.describe_vpcs`
**What goes wrong:** Suffix anchor finds both top-level `Tags.Name` and nested `EncryptionControl.Tags.Name`.
**How to avoid:** Accept it. Aggregation indicator (`(+1 more)`) handles the rare collision. Switching to `^Tags.Name$` (exact) would miss nested instances if a user actually wants them.

### P6 — Audit reports false positives on `value$` for list-of-primitive data fields
**What goes wrong:** Executor may "fix" working defaults (e.g. `ecs.list_clusters value$`).
**How to avoid:** Manual review of every audit-flagged entry. Audit is a candidate detector, not a verdict.
**Warning signs:** audit flags entries the user didn't list as broken.

### P7 — `ssm.get_parameters Parameters$` is broken but OUT OF SCOPE
**Why:** Data-field extraction strips `Parameters` before flatten; `Parameters$` can never match.
**How to avoid:** Document the finding, defer to a follow-up issue. Do not scope-creep.

### P8 — argcomplete has no column-name completer for `+<TAB>`
**Why:** Today's CLI has no column-name completer at all. Not a regression.
**How to avoid:** Document. Defer real column-name completion to a future issue.

## Environment Availability

| Dependency              | Required by                  | Available locally? | Version                  | Fallback                |
|-------------------------|------------------------------|--------------------|--------------------------|-------------------------|
| Python                  | All                          | yes                | 3.10+ baseline           | n/a                     |
| boto3                   | ShapeCache / audit           | yes (1.43.18)      | ≥1.34.0 pyproject        | n/a                     |
| moto                    | Integration tests            | yes (test dep)     | per pyproject            | n/a                     |
| PyYAML                  | YAML loader + audit          | yes (≥6.0)         | per pyproject            | n/a                     |
| argcomplete             | CLI                          | yes (3.6.3)        | per pyproject            | n/a                     |
| tabulate                | Table output                 | yes (0.10.0)       | per pyproject            | n/a                     |
| graphify CLI            | RESEARCH (this run)          | yes                | `/usr/local/bin/graphify`| grep + Read              |
| pre-built graph.json    | RESEARCH                     | yes                | 3,616 nodes / 5,217 edges; built 2026-06-01 | `graphify update /workspace` |

## Graphify usefulness

**Setup verified:** `/workspace/graphify-out/graph.json` is current (built 2026-06-01, same day as research), 3,616 nodes / 5,217 edges. MCP config exists at `.worktrees/.mcp/sue5t-….json`. The graph IS populated (passing the mandated non-zero check); confidence ratio for code modules looked at is HIGH (the call edges to `apply_default_filters`, `transform_tags_structure`, `parse_filter_pattern` were all `confidence=EXTRACTED`).

**Queries tried and their outcomes:**

| Query                                                      | Tool                                       | Result                                                                                                                       | Verdict                          |
|------------------------------------------------------------|--------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|----------------------------------|
| Who calls `apply_default_filters`?                         | Direct JSON traversal of `links`           | 1 source-code caller (`determine_column_filters`), 5 test callers, plus container/rationale edges                            | **HIGH value**                   |
| Who calls `transform_tags_structure`?                      | Direct JSON traversal                      | 6 source callers (flatten_response, format_table/json_output, extract_and_sort_keys, filter_resources, extract_parameter_values) | **HIGH value** — surfaced filter.py callers I'd have missed in a quick grep |
| Path from `main` to `apply_default_filters`                | `graphify path "cli.py main" "apply_default_filters"` | `cli.py --contains--> determine_column_filters --calls--> apply_default_filters` (2 hops)                          | **HIGH value** — confirms strip site |
| Path from `main` to `transform_tags_structure`             | `graphify path "main" "transform_tags_structure"` | `main --calls--> flatten_response --calls--> transform_tags_structure`                                                  | **HIGH value**                   |
| Top god nodes (degree)                                     | Direct traversal of `links`                | `main` (85), `ShapeCache` (83), `smart_select_columns` (79), `find_hint_function` (79), `FilterValidator` (69), …            | Confirms MAP.md core list        |
| What depends on `parse_filter_pattern`?                    | Direct JSON traversal                      | 3 source callers (filter_validator, formatters.filter_columns, filters.filter_resources)                                     | **HIGH value** — confirms grammar isolation |
| `graphify query "Who calls apply_default_filters?"`        | `graphify query "..."`                     | Returned 3 noisy test-file fragments; keyword-BFS, no symbol-level call semantics                                            | **LOW value** — generic CLI query is noisy |
| `graphify explain "apply_default_filters"`                 | `graphify explain "..."`                   | Resolved to a TEST rationale node, not the source function                                                                  | **LOW value** — fuzzy node matching surfaces tests first |

**Verdict: worth integrating into research by default — but USE THE JSON, NOT THE CLI QUERY.**

The pattern that paid off was direct JSON traversal: `nodes_by_id`, `links` filtered by `(target=<func>, context='call')` for callers, the symmetric query for callees. Resolution of source-function nodes follows the convention `awsquery_<module>_<func>`, which is predictable from the file path. The five concrete questions from CONTEXT.md D6 were answered in seconds with high accuracy, including 1-hop and 2-hop paths.

The `graphify query "..."` CLI is a keyword-BFS — useful for high-level "what's near this concept?" exploration but inferior to grep for precise "where is this function called?" questions. `graphify explain` is similar: its node resolution prioritizes degree-1 connections, which often surfaces tests over source.

**Recommendation for future issues:** read `graphify-out/graph.json` directly via Python (no CLI), build `nodes_by_id` and `links_by_target/source` indices, query by `awsquery_<module>_<func>` ID convention. Treat `graphify query`/`graphify explain` as a discovery aid only.

**Specific CONTEXT.md D6 questions:**

- "Who calls `apply_default_filters`?" — `determine_column_filters` only (in src/). 5 test callers. ✅ **paid off**
- "Who calls `transform_tags_structure`?" — 6 source callers (relevant for D5 audit since the transform is the simulation target). ✅ **paid off**
- "What are the callees of `parse_multi_level_filters_for_mode`?" — only `debug_print`; called from `main()` only. ✅ **paid off** (confirms minimal blast radius for any `+` work upstream).
- "What depends on `parse_filter_pattern`?" — `filter_validator.validate_single_column`, `formatters.filter_columns`, `filters.filter_resources`. ✅ **paid off** (confirms `+`-strip must happen UPSTREAM of all three).

All four D6 questions answered with graphify in well under a minute. A grep+Read pass would have taken longer and risked missing the cross-module edge from `filter_validator` (which `_validate_single_column` indirectly imports `parse_filter_pattern`).

## Sources

### HIGH confidence
- Live verification of every CLI/filter code path in this worktree's venv (after `pip install -e .`)
- Live `ShapeCache.get_response_fields` introspection on ec2, ecr, redshift, sns, sqs, directconnect, ssm
- Audit prototype run against full `default_filters.yaml` (1,861 entries → 33 candidate broken → 5-7 actually broken after manual review)
- Graphify JSON traversal for all 4 CONTEXT.md D6 questions
- Direct source inspection of `config.py`, `cli.py`, `filters.py`, `formatters.py`, `shapes.py`, `filter_validator.py`, `auto_filters.py`, `default_filters.yaml`, `tests/unit/test_default_column_filters.py`, `tests/unit/test_filter_implementation.py`
- argparse `+Foo` positional behavior verified live

### MEDIUM confidence
- directconnect transform behavior (P1) — derived from reading `_is_aws_tags_structure` source + the lowercase-key shape; planner should add a live or stubbed integration test to lock the behavior

### LOW confidence
- (none — nothing required unverified web search)

## Metadata

**Confidence breakdown:**
- Codebase analysis: HIGH (every claim cross-referenced with source + live exec)
- Standard stack: HIGH (no new deps)
- Architecture/pattern: HIGH (mandated by CONTEXT.md locked decisions)
- Pitfalls: MIXED — most HIGH; P1 (directconnect transform) is MEDIUM pending live confirmation
- Graphify usefulness: HIGH (direct measurement, verdict supported by 4-of-4 D6 questions)

**Research date:** 2026-06-01
**Sub-agents used:** integrated (single-pass; codebase + ecosystem + pitfalls + graphify evaluation merged inline by the lead researcher)
**Raw research files:** `.issues/sue5t-fix-tags-default-filters-and-add-additive-column-syntax/research/codebase.md`, `…/research/ecosystem.md`, `…/research/pitfalls.md`

**Ready for planning.** All four D6 graphify questions answered; all 1,861 `$`-suffix entries audited; `+Foo` confirmed safe end-to-end; directconnect lowercase-key risk surfaced and a fix path proposed; test placement decided; CLAUDE.md mandatory-agent constraints captured.
