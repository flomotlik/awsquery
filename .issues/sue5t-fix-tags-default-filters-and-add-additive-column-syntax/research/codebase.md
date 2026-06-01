# Codebase research — sue5t

## Data flow: how column filters reach the formatter

End-to-end path verified via graphify (`graphify path` + direct `links` traversal of `graph.json`):

```
cli.main()
  → parse_known_args (first pass)
  → _process_remaining_args / _process_remaining_args_after_separator   # flag/non-flag split
  → _build_filter_argv                                                  # reassembles argv minus flags
  → parse_multi_level_filters_for_mode(filter_argv, mode="single")      # filters.py:136
        returns (base_command, resource_filters, value_filters, column_filters)
  → column_filters = [sanitize_input(f) for f in column_filters]        # cli.py:810
  → determine_column_filters(column_filters, service, action, json_output)   # cli.py:329
        if column_filters:                                              # cli.py:331  ← TODAY: pass-through if any user cols
            column_filters_to_use = column_filters
        else:
            default_columns = apply_default_filters(service, normalized_action)   # config.py:55
            ...
        FilterValidator().validate_columns(service, action, column_filters_to_use)   # cli.py:384
  → format_table_output(filtered_resources, final_column_filters) | format_json_output(...)
        → filter_columns(flattened_data, column_filters)                # formatters.py:127
              → parse_filter_pattern(filter_text)                       # filters.py:12
              → matches_pattern(key, pattern, mode)                     # filters.py:49 (case-insensitive)
```

**Where `+`-prefix stripping cleanly slots in:** the simplest, lowest-risk spot is **inside `determine_column_filters`** (`cli.py:329-396`) at the very top — partition `column_filters` into `additive_columns` (those starting with `+`) and `bare_columns`, strip the `+`, then drive the merge from there. Reasons:

1. `column_filters` arrives already-tokenized and `sanitize_input`-cleaned. Nothing downstream of `determine_column_filters` needs to know about `+`.
2. `apply_default_filters` only needs a tiny extension (new `additive=True` flag or accept a tuple of `(bare, additive)`).
3. The CLAUDE.md "zero backwards compat" allows changing the `apply_default_filters` signature freely.
4. `FilterValidator.validate_columns` (called inside `determine_column_filters`) MUST receive `+`-stripped patterns — its `parse_filter_pattern` doesn't know about `+`. Validation must happen on the merged, stripped list.
5. Doing it later (in `parse_filter_pattern` or `matches_pattern`) would leak the additive concept into the filter grammar layer, which D7 explicitly forbids.

**Open Q from CONTEXT.md (`cli.py` vs `filters.py` for the strip):** lean `cli.py` confirmed. `parse_filter_pattern` is purely about the `^…$` grammar; `+` is a CLI-level mode flip with no pattern semantics.

## How filters use the response shape after transform

`transform_tags_structure` (`formatters.py:206`) rewrites every `{Tags: [{Key:k, Value:v}, ...]}` it finds at any nesting depth into `{Tags: {k:v, ...}}`. Then `flatten_dict_keys` (`formatters.py:351`) walks the dict with `.` separator.

Concrete effect (verified live with `flatten_dict_keys({"Tags": ["v1","latest"]})`):

| Original shape                      | After transform                | After flatten                            |
|-------------------------------------|--------------------------------|------------------------------------------|
| `Tags: [{Key:Name, Value:web}, ...]` | `Tags: {Name: web, ...}`       | `Tags.Name`, `Tags.Environment`, ...     |
| `imageTags: ["v1.0", "latest"]`     | unchanged (no Key/Value pair)  | `imageTags.0: v1.0`, `imageTags.1: latest` |
| `Vpcs: [{VpcId, ...}, ...]`         | unchanged                      | `Vpcs.0.VpcId`, `Vpcs.0.CidrBlock`, ...  |
| `[{value: "arn:..."}, ...]`         | non-dict items wrapped         | each item: `{value: "arn:..."}`          |

`matches_pattern` (`filters.py:49-70`) lowercases BOTH sides — runtime matching is **case-insensitive**. Audit logic must mirror that.

## Audit machinery — what's needed

A working prototype (≈80 LOC, see this file's appendix) using `ShapeCache.get_response_fields` already discriminates 5 categories across all 1,961 `$`-suffix entries:

| Verdict                       | Count | Notes                                                              |
|-------------------------------|------:|--------------------------------------------------------------------|
| Correct (literal match)       |  1819 | Post-transform key exists ending with `<base>` (case-insens)        |
| Correct (K/V dyn target)      |     1 | `Tags.Foo$` style where `<lhs>` is a K/V tag base                   |
| Correct (map-wildcard shape)  |     8 | `sns/sqs get-*-attributes` — `Attributes: map<string,string>`       |
| Broken                        |    33 | See breakdown below                                                 |
| Unverified                    |     0 | All shapes loadable                                                 |

**Audit logic the planner should bake in (heuristic, manual review still required):**

1. Load `simplified_fields` via `ShapeCache.get_response_fields(svc, op-dash)`.
2. Short-circuit if `simplified_fields == {'*': 'map-wildcard'}` (always valid).
3. Detect K/V tag bases case-insensitively: any field `<base>` where `<base>.key` and `<base>.value` both exist as `string`. Collect `kv_bases`.
4. Build `kv_endings` = all path-suffixes of every K/V base (e.g. `Instances.Tags` → `{instances.tags, tags}`).
5. Detect list-of-primitive: any field of type `list` with no `<field>.<member>` children — these flatten to `<field>.0`, `<field>.1`.
6. Build `post_keys` = `simplified_fields.keys()` minus `<kv_base>.key/.value` and bare list-of-primitive parents.
7. For each `<base>$` filter (skipping `^...$`):
   - If `base` contains `.` and the path-prefix is a K/V base ending → **CORRECT** (dynamic K/V target).
   - Else if `base.lower()` doesn't end any `post_keys` → **BROKEN** (no key ends with it).
   - Else if `base.lower()` is itself a `kv_endings` member → **BROKEN** (target IS K/V base; post-transform only `<base>.<dyn>` exists).
   - Else → **CORRECT**.

**ShapeCache reuse:** the existing `ShapeCache` in `src/awsquery/shapes.py` is fully reusable. No extension required. The `_flatten_shape` helper (lines 191-250) already models list-of-struct (`.0` notation), but the audit needs to ADD list-of-primitive detection on top.

**Heuristic limits — the planner MUST highlight to the executor:**

- `value$` against a list-of-primitive top-level data field (e.g. `ecs list_clusters` returning `[arn, arn, ...]`) is CORRECT because `flatten_dict_keys` wraps non-dict items as `{value: item}`. The static-shape detection of `value: list` (pseudo-field added by `get_response_fields` line 121) does not capture this. The audit will false-positive on these unless `value` is explicitly exempt at the top-level data-field case.
- ssm `Parameters: list<{Name, Value, ...}>`: the audit detected `Value` (lowercase) as list-of-primitive, but the actual `Value: string` field also exists. The cross-shape false positive here is a planner concern: run the audit per-service+operation, never globally.
- Manual review of the candidate list is recommended. The audit is a "candidate broken" detector, not a verdict generator.

## Per-service Tags classification (D4)

From the audit's `Broken` set plus directly verified Tag-related entries:

| Service.operation                                        | Current entry      | Replace with     | Why                                                          |
|----------------------------------------------------------|--------------------|------------------|--------------------------------------------------------------|
| `directconnect.describe_direct_connect_gateways`         | `tags$`            | `tags.Name`      | K/V-tagged; AWS Name tag is human label (lowercase key in shape) |
| `ec2.describe_vpcs`                                      | `Tags$`            | `Tags.Name$`     | K/V-tagged; consistent with `ec2.describe_instances` default |
| `redshift.describe_cluster_parameter_groups`             | `Tags$`            | `Tags.Name$`     | K/V-tagged                                                   |
| `redshift.describe_cluster_security_groups`              | `Tags$`            | `Tags.Name$`     | K/V-tagged                                                   |
| `ecr.describe_images`                                    | `imageTags$`       | `imageTags`      | List-of-string; substring match captures `imageTags.0`, `.1` (no `$` anchor) |
| `ecr.list_images`                                        | `imageTag$`        | `imageTag$` (keep) | `imageTag` is `string`, not list (verified via shape). Currently CORRECT. |

`ecr list_images` shape has `imageTag: string` (singular), so `imageTag$` is already valid. The plural `imageTags$` in `ecr describe_images` is the broken one.

`redshift describe_cluster_parameter_groups` has a leftover `Key$` and `Value$` entry (clearly an attempt to surface K/V tag pairs). Both should be deleted as part of this fix — the `Tags.Name$` replacement makes them redundant.

## Test patterns (from `tests/unit/test_default_column_filters.py`)

Style: real implementation, minimal mocking. Tests read `default_filters.yaml` via `load_default_filters()` (cached) and assert against canonical column lists. Existing fixtures:

- `TestLoadDefaultFilters` — caching + structure smoke test
- `TestGetDefaultColumns` — service/action lookup, case-insensitivity, missing keys
- `TestApplyDefaultFilters` — user-columns-replace-defaults assertion (THIS will need updates for additive)
- `TestDetermineColumnFilters` — CLI-layer wrapper
- `TestYAMLConfigurationStructure` — every column is a string, expected services present

For the audit fix: existing tests at `tests/unit/test_default_column_filters.py:107-148` assert `apply_default_filters("ec2", "describe_instances", user_columns)` returns `user_columns` directly when user supplies any. The planner MUST update these to reflect the new additive semantics, AND add new tests:

- `test_additive_merges_with_defaults` — `+Foo` keeps defaults
- `test_additive_with_bare_columns_merges` — `Foo +Bar` keeps defaults + both
- `test_bare_only_still_replaces` — `Foo Bar` replaces (no `+`)
- `test_dedup_case_sensitive` — `+Foo` + default `Foo` → single `Foo`
- `test_additive_ordering` — defaults first, then user-added in CLI order

For test placement: `tests/unit/test_default_column_filters.py` is the right home for the additive logic. `tests/unit/test_filter_implementation.py` covers `parse_filter_pattern`/`matches_pattern` (unchanged by this issue). `tests/unit/test_cli_parser.py` and `tests/unit/test_cli_flags.py` may need additions only if the planner decides to also test the cli.py-level `+`-prefix detection (recommended).

**CLAUDE.md compliance for tests:**
- `@agent-test-writer` is MANDATORY for all test work (CLAUDE.md line 33-40).
- No `@pytest.mark.*` decorators except `parametrize` (CLAUDE.md line 220-243).
- No TDD-placeholder docstrings (CLAUDE.md line 173-205). Use test-name self-documentation.
- Mock only boto3/file I/O; never mock the units under test (CLAUDE.md line 109-167).

## Filter parsing edge cases — leading `+`

Live-verified with `parse_filter_pattern`:

| Input        | Returns           | Mode       | Notes                              |
|--------------|-------------------|------------|------------------------------------|
| `+Foo`       | `('+Foo', 'contains')` | contains   | `+` is literal, matches nothing (no key contains `+`) |
| `+Foo$`      | `('+Foo', 'suffix')`   | suffix     | Trailing `$` stripped, leading `+` literal |
| `++Foo`      | `('++Foo', 'contains')` | contains   | Both `+` are literal                 |
| `+^Foo$`     | `('+^Foo', 'suffix')`  | suffix     | Only the leading `^` (ASCII or U+02C6) is anchor — `+^Foo` literal in pattern body |

**Result:** `+` has NO current grammar meaning. Repurposing it for CLI-level additive mode has **zero collision risk** with the existing pattern grammar.

**Per CONTEXT.md D7:** `+`-stripping happens BEFORE `parse_filter_pattern` ever sees the token. The filter grammar is untouched.

## CLI tokenization risk — `+Foo` as argparse positional

Live-verified:

- `argparse` with default `prefix_chars='-'` does NOT interpret `+Foo` as an option. `+Foo` flows through as a positional/remaining arg unchanged.
- `_process_remaining_args` / `_process_remaining_args_after_separator` (cli.py:259-295): both filter `SIMPLE_FLAGS`/`VALUE_FLAGS` lists; neither contains `+` — `+Foo` is preserved.
- `_build_filter_argv` (cli.py:298-319): same logic; `+Foo` passes through.
- `parse_multi_level_filters_for_mode` (filters.py:136): only splits on literal `--`; `+`-prefixed tokens are preserved verbatim.
- Shell quirks: bash/zsh default config treats `+` as plain text. Only bash's `extglob` (`+(pattern)`) repurposes `+`, and only when explicitly enabled. Not a real-world concern for `+Foo` literal tokens.
- argcomplete: completes against the standard argparse object. `+Foo` is a positional input; argcomplete doesn't apply special semantics. (Recommendation: planner add a regression test asserting `awsquery ec2 describe-instances +Foo` parses cleanly.)

## Interfaces (the crown jewel for the planner)

<interfaces>
// From src/awsquery/config.py — TODAY
def load_default_filters() -> dict
def get_default_columns(service: str, action: str) -> list[str]
def apply_default_filters(service: str, action: str, user_columns: list[str] | None = None) -> list[str] | None
    # TODAY: returns user_columns directly if any are provided; else loads defaults; else None
    # CHANGE: add additive support — recommended new shape (CLAUDE.md ZERO backwards compat → free to break):
    #   def apply_default_filters(service, action, user_columns=None, additive=False) -> list[str] | None
    #   When additive=True: merge defaults + user_columns (defaults first, then user in arg order; dedup case-sensitive)

// From src/awsquery/cli.py
def determine_column_filters(
    column_filters: list[str] | None,
    service: str,
    action: str,
    json_output: bool = False
) -> list[str] | None
    # The integration point. Partition column_filters into (additive_present, bare_columns, additive_columns_stripped)
    # If additive_present: column_filters_to_use = apply_default_filters(service, action, user_columns=merged, additive=True)
    # Else (today's branch): bare-only → user-columns replace defaults; empty → defaults

# Surrounding helpers (unchanged but referenced by main() pipeline)
def _process_remaining_args(remaining: list[str]) -> tuple[list[str], list[str]]
def _process_remaining_args_after_separator(remaining: list[str]) -> tuple[list[str], list[str]]
def _build_filter_argv(args, remaining: list[str]) -> list[str]
def _format_columns_copyable(columns: list[str]) -> str
    # NOTE: when defaults are echoed to stderr in additive mode, planner should consider showing
    # "Using default columns + additions: -- DefaultA DefaultB +UserC"

# main() pipeline (the consumer)
# cli.py:797 — parse_multi_level_filters_for_mode(filter_argv, mode="single") → (_, resource_filters, value_filters, column_filters)
# cli.py:810 — column_filters = [sanitize_input(f) for f in column_filters]
# cli.py:962 — final_column_filters = determine_column_filters(column_filters, service, action, json_output=args.json)
# cli.py:1084/1086 — format_json_output(filtered_resources, final_column_filters) | format_table_output(...)

// From src/awsquery/filters.py
def parse_filter_pattern(filter_text: str) -> tuple[str, str]
    # Returns (pattern, mode) where mode ∈ {'exact','prefix','suffix','contains'}
    # NOT TOUCHED by this issue. `+` has no meaning here and stays that way.
def matches_pattern(text, pattern, mode) -> bool
    # Lowercases both sides — CASE-INSENSITIVE. Audit must match.
def filter_resources(resources, value_filters) -> list[dict]
def parse_multi_level_filters_for_mode(argv, mode="single") -> tuple[list, list, list, list]
    # Returns (base_command, resource_filters, value_filters, column_filters).
    # `+Foo` tokens pass through into column_filters unchanged.

// From src/awsquery/formatters.py
def transform_tags_structure(data, max_depth=10, current_depth=0)
    # Recursively rewrites {Tags: [{Key,Value}, ...]} → {Tags: {Key: Value, ...}}
    # Only when Key/Value are exact (case-sensitive!) members. directconnect uses lowercase 'key'/'value' —
    # audit must verify whether transform actually fires there. (See _is_aws_tags_structure formatters.py:195.)
def flatten_dict_keys(d, parent_key="", sep=".") -> dict
    # Lists-of-dict → "<parent>.<i>.<child>"; lists-of-primitive → "<parent>.<i>"; non-dict input → {"value": d}
def filter_columns(flattened_data, column_filters) -> dict
def format_table_output(resources, column_filters=None, max_width=None) -> str
def format_json_output(resources, column_filters=None) -> str
def detect_aws_tags(obj) -> bool
def _is_aws_tags_structure(value) -> bool

// From src/awsquery/shapes.py — REUSE for the audit, no extension needed
class ShapeCache:
    def get_service_model(self, service: str) -> ServiceModel | None
    def get_operation_shape(self, service: str, operation: str)
    def get_response_fields(self, service: str, operation: str) -> tuple[str | None, dict[str,str], dict[str,str]]
        # Returns (data_field, simplified_fields, full_fields). Audit uses simplified_fields.
        # NB: simplified_fields adds {'value': 'list'} pseudo-field when data field is a top-level list-of-primitive.
    def get_fields_for_auto_select(self, service: str, operation: str) -> dict[str,str]

// From src/awsquery/filter_validator.py — IMPORTANT short-circuits
class FilterValidator:
    def validate_columns(self, service, operation, column_filters: list[str]) -> list[tuple[str, str|None]]
        # CRITICAL: short-circuits for 'tag' in filter.lower() (line 85) — Tags get a free pass.
        # Also short-circuits for map-wildcard shapes (line 79).
        # So +Tags.Name is auto-valid; +ArbitraryColumn goes through full validation.
        # The validator must receive +-STRIPPED patterns from determine_column_filters.

// directconnect: investigate before fix
# Shape uses lowercase 'tags.key' / 'tags.value' which transform_tags_structure WILL NOT match
# (_is_aws_tags_structure on formatters.py:195 requires literal 'Key' and 'Value' string keys, case-sensitive).
# Therefore directconnect's `tags$` won't even be visible as 'tags.<dyn>' post-transform — it stays a
# list of dicts and flattens to 'tags.0.key', 'tags.0.value', 'tags.1.key', ...
# Replacing `tags$` with `tags.Name` may NOT work at runtime because the transform doesn't fire.
# Planner must:
#   (a) test directconnect describe-direct-connect-gateways live (or with a stubbed response) to confirm shape
#   (b) decide: either fix _is_aws_tags_structure to also accept lowercase 'key'/'value', or replace
#       directconnect's `tags$` with the substring pattern `tags.key` / `tags.value` / `tags` (contains-match).
# Recommendation: fix `_is_aws_tags_structure` to accept case-variant Key/Value (one-line change), which is also
# more correct for any other lowercase-key services. Document this as a sub-decision in the plan.
</interfaces>

## Audit prototype (drop-in reference, 90 LOC)

```python
"""Audit broken $-suffix entries against shape + transform model.

Run from repo root:
    python3 scripts/audit_default_filters.py
"""
import yaml
from awsquery.shapes import ShapeCache

def _detect_kv_bases(simp):
    bases, by_lower = set(), {k.lower(): k for k in simp}
    for k, t in simp.items():
        if not k.lower().endswith('.key') or t != 'string': continue
        base_l = k.lower()[:-4]
        val_l = f"{base_l}.value"
        if val_l in by_lower and simp[by_lower[val_l]] == 'string':
            bases.add(k[:-4])
    return bases

def _detect_list_of_primitive(simp):
    return {k for k, t in simp.items() if t == 'list' and not any(c.startswith(f"{k}.") for c in simp)}

def _kv_endings(kv_bases):
    out = set()
    for kb in kv_bases:
        parts = kb.split('.')
        for i in range(len(parts)):
            out.add('.'.join(parts[i:]).lower())
    return out

def audit_default_filters(config_path='src/awsquery/default_filters.yaml'):
    sc = ShapeCache()
    cfg = yaml.safe_load(open(config_path))
    report = {'broken': [], 'correct': [], 'wildcard': [], 'kv_dyn': [], 'unverified': []}

    for svc, actions in cfg.items():
        for op, opcfg in actions.items():
            cols = opcfg.get('columns', []) or []
            op_dash = op.replace('_', '-')
            try:
                _, simp, _ = sc.get_response_fields(svc, op_dash)
            except Exception as e:
                for col in cols:
                    if col.endswith('$') and not col.startswith('^'):
                        report['unverified'].append((svc, op, col, f"shape err: {type(e).__name__}"))
                continue
            if not simp:
                for col in cols:
                    if col.endswith('$') and not col.startswith('^'):
                        report['unverified'].append((svc, op, col, 'empty shape'))
                continue
            if simp.get('*') == 'map-wildcard':
                for col in cols:
                    if col.endswith('$') and not col.startswith('^'):
                        report['wildcard'].append((svc, op, col))
                continue
            kv_bases = _detect_kv_bases(simp)
            list_prim = _detect_list_of_primitive(simp)
            list_prim_lower = {p.lower() for p in list_prim}
            kv_drop_lower = {f"{kb.lower()}.key" for kb in kv_bases} | {f"{kb.lower()}.value" for kb in kv_bases}
            post_keys = {k for k in simp if k.lower() not in kv_drop_lower and k.lower() not in list_prim_lower}
            kv_endings = _kv_endings(kv_bases)

            for col in cols:
                if not col.endswith('$') or col.startswith('^'): continue
                base, bl = col[:-1], col[:-1].lower()
                # K/V dynamic target like Tags.Name$
                if '.' in base:
                    lhs = base.rsplit('.', 1)[0].lower()
                    lhs0 = base.split('.', 1)[0].lower()
                    if any(lhs == e or lhs.endswith('.' + e) for e in kv_endings) or lhs0 in kv_endings:
                        report['kv_dyn'].append((svc, op, col))
                        continue
                matches = [k for k in post_keys if k.lower().endswith(bl)]
                if not matches:
                    if bl in list_prim_lower:
                        report['broken'].append((svc, op, col, f"list-of-primitive → flattens to {base}.0..N"))
                    else:
                        report['broken'].append((svc, op, col, 'no key ends with'))
                    continue
                if bl in kv_endings:
                    report['broken'].append((svc, op, col, f"target IS K/V base → post-transform {base}.<dyn> only"))
                    continue
                report['correct'].append((svc, op, col, matches[:3]))
    return report

if __name__ == '__main__':
    r = audit_default_filters()
    print(f"Broken: {len(r['broken'])}, Correct: {len(r['correct'])}, "
          f"K/V dyn: {len(r['kv_dyn'])}, Wildcard: {len(r['wildcard'])}, "
          f"Unverified: {len(r['unverified'])}")
    for b in r['broken']:
        print(f"  BROKEN  {b[0]}.{b[1]:50} : {b[2]:35}  -- {b[3]}")
```

**Known false-positives this prototype produces (manual review required):**
- `ecs.list_clusters value$`, `eks.list_*  value$`, etc.: `value$` is the correct pattern when data field is list-of-primitive (each item wraps to `{value: item}` via `flatten_dict_keys`).
- `ssm.get_parameters Value$`: `Value: string` exists in the per-parameter struct; the `value: list` pseudo-field is the orthogonal data-field metadata.
- The planner should add a top-level data-field-list-of-primitive exemption: if `simplified_fields.get('value') == 'list'` AND `<base>.lower() == 'value'`, treat as CORRECT.

## Recent git activity on relevant files

```
$ git log --oneline -10 -- src/awsquery/config.py src/awsquery/cli.py src/awsquery/filters.py src/awsquery/default_filters.yaml
```
The relevant files have been stable since the auto-filters feature merged. No pending PRs touch this area. Safe to plan/execute.
