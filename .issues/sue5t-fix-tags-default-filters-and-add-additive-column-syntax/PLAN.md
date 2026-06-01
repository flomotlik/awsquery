# Plan: Fix Tags$ default filters and add additive +Column syntax

<objective>
What this plan accomplishes:
1. Fix the 5 truly broken `Tags$`-class entries in `default_filters.yaml` (plus delete 2 redundant `Key$`/`Value$` leftovers under redshift) so that `ec2 describe-instances`, `ec2 describe-vpcs`, `directconnect describe-direct-connect-gateways`, the redshift `describe_cluster_*` operations, and `ecr describe-images` all show populated Name/tag columns by default.
2. Patch `formatters._is_aws_tags_structure` + `_transform_aws_tags_list` to accept case-variant `Key`/`Value` member names (unblocks directconnect, whose botocore shape uses lowercase `key`/`value`).
3. Add additive `+Column` CLI syntax: any `+`-prefixed column in the column-filter group switches the invocation into additive mode (defaults + user columns, order-preserving dedup); bare `Column` keeps today's replace-defaults behaviour.
4. Ship a re-runnable shape-aware audit (`scripts/audit_default_filters.py`) plus a unit test that runs it against the shipped YAML and asserts the in-scope broken entries no longer appear.
5. Document `+Column` in the README's filter section.

Why it matters: today every default with `Tags$` produces empty Name columns post-`transform_tags_structure` flattening (the runtime sees `Tags.Name`, never `Tags`), and there is no way to opt in to defaults while adding one extra column. Both are recurring papercuts.

Scope:
- IN: `src/awsquery/config.py`, `src/awsquery/cli.py`, `src/awsquery/formatters.py`, `src/awsquery/default_filters.yaml`, `scripts/audit_default_filters.py` (new), `tests/unit/test_default_column_filters.py`, `tests/unit/test_tags_transformation.py`, `tests/unit/test_cli_parser.py` (or `test_cli_flags.py`), `README.md`.
- OUT: filter grammar (`^...$`) untouched; no `-Column` subtractive syntax; no `--additive` flag; no YAML restructuring; `ssm.get_parameters Parameters$` finding is deferred to a follow-up issue (per RESEARCH.md P7).
</objective>

<strategy>
The two halves of this issue look unrelated but share a single funnel: `cli.py::determine_column_filters` is where user column arguments meet defaults, and `formatters.transform_tags_structure` is the post-fetch transform whose output the YAML defaults must anchor against. Both halves get small, surgical changes at those two sites.

**The direction:** keep the filter grammar untouched (CONTEXT.md D7), strip the `+` prefix at the CLI funnel before any validator/grammar code sees it, and merge `defaults + stripped_user_cols` with `list(dict.fromkeys(...))` for order-preserving dedup. For the YAML, fix only the 5 truly broken entries surfaced by the static shape-aware audit (CONTEXT.md D5) — no global rewrite — and unblock directconnect with a 1-line case-insensitive companion patch to `_is_aws_tags_structure`.

**Strategic options considered:**

1. **Strip `+` in `determine_column_filters` (CHOSEN)** vs strip in `parse_filter_pattern`. The grammar layer would leak CLI semantics if it knew about `+`; D7 forbids it; and `FilterValidator` runs inside `determine_column_filters`, so it must receive `+`-stripped tokens. Single funnel, zero collisions with `parse_filter_pattern`, `parse_multi_level_filters_for_mode`, argparse, or `_process_remaining_args*` (RESEARCH.md verified all four live).

2. **Per-service YAML fix (CHOSEN)** vs global `Tags$` to `Tags.Name$` rewrite. The audit shows only 5 broken Tags-class entries; a global rewrite would break list-of-string-tagged services. CONTEXT.md D4 picks per-service.

3. **Fix `_is_aws_tags_structure` to accept lowercase keys (CHOSEN)** vs replacing directconnect's `tags$` with bare `tags.0.key`/`tags.0.value` literals. The transform fix is one line, helps every other lowercase-key service in the future, and keeps the YAML clean.

4. **Re-runnable audit script + unit test that runs it (CHOSEN)** vs snapshot of corrected YAML. Snapshots drift the moment boto3 ships new shapes; the script is self-updating and the test gives CI a regression guard without a separate run.

**Key decision points (the four locked CONTEXT.md decisions):**
- D1: any `+`-prefix anywhere in the column-filter group flips the whole invocation into additive mode.
- D2: merge order is `defaults + user_cols`; dedup is case-sensitive on the full pattern string via `dict.fromkeys`.
- D3: `+` applies only to the column-filter group; value/resource filters are untouched.
- D4: per-service Tags fix, audit-driven.

Sequencing is bottom-up: extend `apply_default_filters` first (pure data, easy tests), then wire the CLI funnel, then patch the formatter for directconnect, then fix YAML, then add audit + tests, then docs, then review.
</strategy>

<skills>
No workspace skills directory (`.claude/skills/`) is present in this repo. CLAUDE.md instead mandates specialized agents — the executor must:
- delegate every Python implementation task to `@agent-python-infra-automator`
- delegate every test creation/modification task to `@agent-test-writer`
- run `@agent-code-reviewer` on significant changes (Task 9)
</skills>

<context>
Issue: @.issues/sue5t-fix-tags-default-filters-and-add-additive-column-syntax/ISSUE.md
Research: @.issues/sue5t-fix-tags-default-filters-and-add-additive-column-syntax/RESEARCH.md
Decisions: @.issues/sue5t-fix-tags-default-filters-and-add-additive-column-syntax/CONTEXT.md
Codebase notes (audit prototype + interfaces): @.issues/sue5t-fix-tags-default-filters-and-add-additive-column-syntax/research/codebase.md
Project guide: @CLAUDE.md
Map: @.issues/MAP.md

<interfaces>
<!-- Executor: use these contracts directly. Do not explore the codebase for them. -->
<!-- All signatures verified against the worktree's actual source on 2026-06-01. -->

From src/awsquery/config.py (CURRENT - to be extended in Task 1):

  @lru_cache(maxsize=1)
  def load_default_filters() -> dict   # cached YAML loader; do NOT touch

  def get_default_columns(service: str, action: str) -> list[str]
      # Returns the columns list (may be empty); does service.lower()/action.lower() lookup.

  def apply_default_filters(service: str, action: str, user_columns: list[str] | None = None) -> list[str] | None
      # TODAY: if user_columns: return user_columns; elif defaults: return defaults; else None.
      # NEW SIGNATURE (Task 1):
      #   def apply_default_filters(service, action, user_columns=None, additive=False) -> list[str] | None
      #   additive=True AND user_columns non-empty:
      #       defaults = get_default_columns(service, action) or []
      #       merged = list(dict.fromkeys(defaults + user_columns))   # case-sensitive, order-preserving
      #       return merged or None
      #   additive=False (today's path): unchanged.

From src/awsquery/cli.py:

  def _format_columns_copyable(columns: list[str]) -> str
      # cli.py:322. Today: returns "-- " + " ".join(columns) when non-empty.
      # NEW SIGNATURE (Task 3):
      #   def _format_columns_copyable(columns, additive_marks: list[bool] | None = None) -> str
      # When additive_marks is provided, render the matching positions with a leading '+'.

  def determine_column_filters(
      column_filters: list[str] | None,
      service: str,
      action: str,
      json_output: bool = False,
  ) -> list[str] | None
      # cli.py:329. Single funnel between parsed user column args and FilterValidator + apply_default_filters.
      # Task 2 adds a guard at the TOP of the function:
      #   additive_present = any(isinstance(c, str) and c.startswith('+') for c in (column_filters or []))
      #   if additive_present: strip '+'; call apply_default_filters(..., additive=True); echo to stderr; fall through to validator.
      #   else: today's branches unchanged.

From src/awsquery/filters.py - UNCHANGED by this issue (verified):

  def parse_filter_pattern(filter_text: str) -> tuple[str, str]
      # '+' has NO grammar meaning. Never modify.
  def matches_pattern(text, pattern, mode) -> bool   # case-insensitive runtime match
  def parse_multi_level_filters_for_mode(argv, mode="single") -> tuple[list, list, list, list]
      # '+Foo' tokens pass through into column_filters unchanged.

From src/awsquery/formatters.py - TO BE PATCHED in Task 4:

  def _is_aws_tags_structure(value) -> bool
      # formatters.py:195. TODAY: case-sensitive - requires literal 'Key' and 'Value'.
      # NEW: accept any case variant. Resolve via lower-cased member-name set.

  def _transform_aws_tags_list(tags_list) -> dict
      # formatters.py:183. TODAY: hard-codes tag["Key"]/tag["Value"].
      # NEW: case-insensitive member access (first match wins; bail if either missing).

  def transform_tags_structure(data, max_depth=10, current_depth=0)
      # Caller of _is_aws_tags_structure / _transform_aws_tags_list. UNCHANGED.

  def flatten_dict_keys(d, parent_key="", sep=".") -> dict
      # UNCHANGED. Lists-of-dict -> "<parent>.<i>.<child>"; lists-of-primitive -> "<parent>.<i>";
      # non-dict d -> {"value": d}.

From src/awsquery/shapes.py - REUSE for audit:

  class ShapeCache:
      def get_response_fields(self, service: str, operation: str) -> tuple[str | None, dict[str, str], dict[str, str]]
          # Returns (data_field, simplified_fields, full_fields). Audit uses simplified_fields.

From src/awsquery/filter_validator.py - IMPORTANT short-circuits (UNCHANGED):

  class FilterValidator:
      def validate_columns(self, service, operation, column_filters: list[str]) -> list[tuple[str, str | None]]
          # Short-circuits on 'tag' in filter.lower() (line 85). Receives '+'-STRIPPED patterns
          # because determine_column_filters strips '+' before calling validate_columns.

New file proposed by Task 6:

  # scripts/audit_default_filters.py
  def audit_default_filters(config_path: str = 'src/awsquery/default_filters.yaml') -> dict
      # Returns {'broken': [...], 'correct': [...], 'wildcard': [...], 'kv_dyn': [...], 'unverified': [...]}.
      # Each 'broken' entry is a tuple (service, operation, filter_str, reason).
      # Audit prototype lives in research/codebase.md - see Task 6 for the canonical port.

</interfaces>

<call_sites>
Searched: `apply_default_filters`, `determine_column_filters`, `_format_columns_copyable`, `_is_aws_tags_structure`, `transform_tags_structure`, `parse_filter_pattern`, the broken `Tags$/tags$/imageTags$/Key$/Value$` YAML entries, and CLI `+Column` usage.
Surfaces grepped: src/, tests/, scripts/, README.md, Makefile, .github/workflows/, docs/.

Found:
- src/awsquery/cli.py:339 — `apply_default_filters(service, normalized_action)` inside `determine_column_filters`. IN SCOPE (Task 1 changes signature; Task 2 adds new additive call path).
- src/awsquery/cli.py:347, 365 — `_format_columns_copyable(default_columns | exact_columns)`. IN SCOPE (Task 3 extends signature; Task 2 calls it with `additive_marks`).
- src/awsquery/cli.py:380 — `FilterValidator().validate_columns(service, action, column_filters_to_use)`. OUT OF SCOPE for code edits; receives `+`-stripped patterns automatically because Task 2 strips `+` upstream. Tests in Task 7 assert NO validator warnings fire for additive runs.
- src/awsquery/cli.py:962 — `final_column_filters = determine_column_filters(...)` inside `main()`. OUT OF SCOPE (caller unchanged; new behaviour entirely inside `determine_column_filters`).
- src/awsquery/cli.py:810 — `column_filters = [sanitize_input(f) for f in column_filters]`. OUT OF SCOPE; `sanitize_input` preserves `+` (verified — only strips control chars / whitespace).
- src/awsquery/formatters.py:220 — `_is_aws_tags_structure(value)` call site inside `transform_tags_structure`. IN SCOPE (Task 4 patches the callee, not this call site).
- tests/unit/test_default_column_filters.py:107-156 — existing `TestApplyDefaultFilters` class. IN SCOPE (Task 7 ADDS new test classes; existing tests keep working because `additive` defaults to `False`).
- tests/unit/test_tags_transformation.py — existing test file for `transform_tags_structure`. IN SCOPE (Task 7 adds lowercase-key fixture cases).
- tests/unit/test_cli_parser.py and tests/unit/test_cli_flags.py — IN SCOPE for Task 7 regression: verify `+Foo` parses cleanly through argparse + helpers.
- README.md:401-451 — `## Advanced Usage` -> `### Filter Matching Behavior` -> `#### Filter Operators` / `#### Column Filters (after \`--\`)`. IN SCOPE (Task 8 documents `+Column`).
- src/awsquery/default_filters.yaml — five line numbers IN SCOPE (Task 5):
  - line 829: `- tags$` under `directconnect.describe_direct_connect_gateways`
  - line 1071: `- Tags$` under `ec2.describe_vpcs`
  - line 1087: `- imageTags$` under `ecr.describe_images`
  - lines 2230-2232: `- Tags$`, `- Key$`, `- Value$` under `redshift.describe_cluster_parameter_groups`
  - line 2241: `- Tags$` under `redshift.describe_cluster_security_groups`
- scripts/ — currently contains only README.md and validate-awsquery.sh; new file `scripts/audit_default_filters.py` is IN SCOPE (Task 6).
- Makefile, .github/workflows/, docs/ — no references to the changed functions or to `+Column`; OUT OF SCOPE.

No additional unexpected call sites found.
</call_sites>

Key files:
@src/awsquery/config.py — `apply_default_filters` signature change (Task 1).
@src/awsquery/cli.py — `determine_column_filters` and `_format_columns_copyable` (Tasks 2-3).
@src/awsquery/formatters.py — `_is_aws_tags_structure`, `_transform_aws_tags_list` (Task 4).
@src/awsquery/default_filters.yaml — 5 lines to edit + 2 to delete (Task 5).
@src/awsquery/shapes.py — read-only consumer for audit (Task 6).
@src/awsquery/filter_validator.py — read-only; verifies short-circuits stay intact (no edits, tests in Task 7).
@tests/unit/test_default_column_filters.py — extend, do NOT create a new file (Task 7).
@tests/unit/test_tags_transformation.py — extend, do NOT create a new file (Task 7).
@tests/unit/test_cli_parser.py — extend or add to `test_cli_flags.py` per existing convention (Task 7).
@scripts/audit_default_filters.py — NEW (Task 6).
@README.md — `## Advanced Usage` filter section (Task 8).
</context>

<commit_format>
Format: plain (single-line summary, max 72 chars, no scope prefix), with the standard CLAUDE.md trailer.
Pattern: `<imperative short description>` then the trailer block exactly as shown.
Example: `Fix broken Tags$ defaults and add additive +Column syntax`
Trailer (verbatim):

    Generated with Claude Code (https://claude.com/claude-code)
    Co-Authored-By: Claude <noreply@anthropic.com>

CLAUDE.md "Git Commit Guidelines" mandates: NO bullets, NO multi-paragraph descriptions, NO multiple unrelated changes per commit. Each task in this plan is one atomic commit.
</commit_format>

<tasks>

<task type="auto">
  <name>Task 1: Extend apply_default_filters for additive merge</name>
  <files>src/awsquery/config.py</files>
  <action>
  MANDATORY: Delegate this implementation to @agent-python-infra-automator per CLAUDE.md. Provide the agent with the full interfaces block from this PLAN and the locked CONTEXT.md D2 decision (defaults-first, case-sensitive dedup via dict.fromkeys).

  Change apply_default_filters in src/awsquery/config.py:55 to accept a new `additive: bool = False` keyword argument. Per CLAUDE.md "ZERO backward compatibility" - change the signature in place, do NOT add a wrapper function or shim.

  New behaviour:
  - When additive=False (default): behaviour is UNCHANGED - preserves all today's call sites.
  - When additive=True AND user_columns is a non-empty list: load defaults via get_default_columns(service, action). If defaults is empty, return user_columns directly (sensible degenerate; equivalent to bare-only with no defaults). Otherwise return list(dict.fromkeys(defaults + user_columns)). Dedup is case-sensitive on the full pattern string (CONTEXT.md D2). dict.fromkeys preserves first-seen order; defaults come first so a default and a textually-identical user entry collapse at the default's position.
  - When additive=True AND user_columns is empty/None: return defaults (same as additive=False, user_columns=None).
  - Use debug_print("Additive mode: merged defaults + user columns: ...") for the additive branch - keep the existing debug-print idiom.

  Do NOT touch load_default_filters (cached, stable) or get_default_columns. Do NOT add a new public function - extend the existing one.

  Constraint: every existing caller of apply_default_filters (notably cli.py:339) MUST continue to work because they all use positional or keyword args that don't collide with the new additive parameter. Verify by grepping `apply_default_filters\(` repo-wide before committing.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && python3 -m pytest tests/unit/test_default_column_filters.py -v --no-cov && grep -rn "apply_default_filters(" src/ tests/ scripts/</automated>
  </verify>
  <done>
  - apply_default_filters accepts `additive: bool = False` keyword arg.
  - additive=True + non-empty user_columns returns list(dict.fromkeys(defaults + user_columns)).
  - additive=True + empty/None user_columns returns defaults (or None if no defaults).
  - additive=False path is byte-identical to today's behaviour.
  - All existing tests in tests/unit/test_default_column_filters.py still pass without modification.
  - grep shows no broken call sites.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add +-prefix detection and additive routing in determine_column_filters</name>
  <files>src/awsquery/cli.py</files>
  <action>
  MANDATORY: Delegate this implementation to @agent-python-infra-automator per CLAUDE.md. Provide the agent with the full determine_column_filters interface block above and the locked CONTEXT.md D1/D3 decisions (any `+` in the column-filter group flips the whole invocation into additive mode; the `+` mechanism applies ONLY to the column-filter group - value/resource filters are untouched).

  Modify determine_column_filters in src/awsquery/cli.py:329. The strip site is at the very top of the function - the single funnel between user input and both FilterValidator.validate_columns and apply_default_filters. RESEARCH.md verified zero collisions with parse_filter_pattern, parse_multi_level_filters_for_mode, argparse, _process_remaining_args, and _build_filter_argv.

  Implementation outline (executor adapts to current code structure but MUST preserve all today's branches when `+` is absent):

      def determine_column_filters(column_filters, service, action, json_output=False):
          from .utils import normalize_action_name
          normalized_action = normalize_action_name(action)

          additive_present = any(isinstance(c, str) and c.startswith('+')
                                 for c in (column_filters or []))

          if additive_present:
              stripped = [c[1:] if isinstance(c, str) and c.startswith('+') else c
                          for c in column_filters]
              debug_print(f"Additive mode detected; stripped columns: {stripped}")
              merged = apply_default_filters(service, normalized_action,
                                             user_columns=stripped, additive=True)
              column_filters_to_use = merged if merged else stripped
              if not json_output:
                  # Render '+' on entries that originated as user-added (not in pure defaults).
                  defaults_only = apply_default_filters(service, normalized_action) or []
                  defaults_set = set(defaults_only)
                  additive_marks = [c not in defaults_set
                                    for c in (column_filters_to_use or [])]
                  cols = _format_columns_copyable(column_filters_to_use,
                                                  additive_marks=additive_marks)
                  print(f"Using default columns + additions: {cols}", file=sys.stderr)
          elif column_filters:
              # TODAY's bare-only branch - unchanged
              debug_print(f"Using user-specified column filters: {column_filters}")
              column_filters_to_use = column_filters
          else:
              # TODAY's defaults / auto-select branch - unchanged
              ... (preserve existing logic verbatim)

          # FilterValidator call at cli.py:380 - UNCHANGED. The validator receives '+'-stripped
          # patterns because we stripped them above before this block.
          ...
          return column_filters_to_use

  CRITICAL constraints:
  - The `+`-strip MUST happen BEFORE FilterValidator.validate_columns is called (RESEARCH.md P2). The validator only short-circuits on `'tag' in filter.lower()`; raw `+InstanceId` would emit a false "matches no fields" warning.
  - _format_columns_copyable must be called with additive_marks for the additive stderr echo to render `+`-prefixed entries as `+Foo` so the echoed command is copy-paste-runnable.
  - When merged is empty (e.g. service.action unknown to defaults), fall back to stripped (raw user columns sans `+`) - never lose the user's input.
  - The bare-only branch (today's path) MUST stay byte-identical when no `+` is present. The strip block is ADDITIVE code, not a rewrite.
  - Do NOT touch parse_filter_pattern, matches_pattern, parse_multi_level_filters_for_mode, _process_remaining_args, _process_remaining_args_after_separator, _build_filter_argv, or sanitize_input. The `+` survives them all (verified live in RESEARCH.md).

  Anti-pattern to avoid: do NOT register `+` as an argparse prefix character. Do NOT add a `--additive` flag (CONTEXT.md D7 defers this).
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && python3 -m pytest tests/unit/test_default_column_filters.py tests/unit/test_cli_parser.py tests/unit/test_cli_flags.py -v --no-cov && python3 -c "from awsquery.cli import determine_column_filters; r = determine_column_filters(['+Tags.Name','VpcId'],'ec2','describe_vpcs',json_output=True); print('result:',r); assert r and not any(str(x).startswith('+') for x in r), '+ should be stripped'; assert 'VpcId' in r"</automated>
  </verify>
  <done>
  - determine_column_filters recognises any `+`-prefixed column anywhere in column_filters and switches to additive mode.
  - `+` prefix is stripped before FilterValidator.validate_columns is called.
  - Additive mode prints "Using default columns + additions: ..." to stderr when json_output is False.
  - When no `+` is present, behaviour is unchanged (existing tests pass).
  - `+Foo Bar` mixed input -> additive mode (defaults + Foo + Bar) per CONTEXT.md D1.
  </done>
</task>

<task type="auto">
  <name>Task 3: Extend _format_columns_copyable to render + prefixes</name>
  <files>src/awsquery/cli.py</files>
  <action>
  MANDATORY: Delegate this implementation to @agent-python-infra-automator per CLAUDE.md.

  Extend _format_columns_copyable in src/awsquery/cli.py:322. Today's signature is `def _format_columns_copyable(columns):`. Add a new keyword arg `additive_marks: list[bool] | None = None`.

  Behaviour:
  - When additive_marks is None, all-False, or len(additive_marks) != len(columns): render exactly as today ("-- " + " ".join(columns)). This keeps the auto-select branch (cli.py:365) and the defaults-only branch (cli.py:347) unchanged.
  - When additive_marks is provided and any entry is True: each column at index i where additive_marks[i] is True is rendered with a leading `+` (e.g. `+Foo`). The leading `-- ` separator stays the same.

  Example:

      _format_columns_copyable(['Tags.Name','VpcId','Foo'], additive_marks=[False,False,True])
      -> '-- Tags.Name VpcId +Foo'

  Why: per RESEARCH.md open question, the stderr echo of the columns must stay copy-paste-runnable. Without `+` prefixes the user could paste the echoed command and lose additive mode (it would degrade to bare-only, replacing defaults).

  Constraints:
  - Default arg value is None - preserves byte-identical behaviour for the two existing call sites at cli.py:347 and cli.py:365.
  - No external dependencies. Pure string assembly.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && python3 -c "from awsquery.cli import _format_columns_copyable; assert _format_columns_copyable(['A','B']) == '-- A B'; assert _format_columns_copyable(['A','B'], additive_marks=[False,True]) == '-- A +B'; assert _format_columns_copyable(['A','B'], additive_marks=None) == '-- A B'; assert _format_columns_copyable(['A','B'], additive_marks=[False,False]) == '-- A B'; print('ok')" && python3 -m pytest tests/unit/test_default_column_filters.py -v --no-cov</automated>
  </verify>
  <done>
  - _format_columns_copyable(cols) returns identical output to today's implementation when additive_marks is None.
  - _format_columns_copyable(cols, additive_marks=[...]) renders `+` prefixes at matching positions.
  - Length mismatch / None handled gracefully (no `+` rendered).
  - Existing call sites at cli.py:347 and cli.py:365 still pass (columns) only; behaviour unchanged for them.
  </done>
</task>

<task type="auto">
  <name>Task 4: Fix _is_aws_tags_structure for case-insensitive Key/Value</name>
  <files>src/awsquery/formatters.py</files>
  <action>
  MANDATORY: Delegate this implementation to @agent-python-infra-automator per CLAUDE.md. Provide the agent with the _is_aws_tags_structure / _transform_aws_tags_list interface blocks and RESEARCH.md Pitfall P1 (directconnect's botocore shape uses lowercase `key`/`value` member names; without this fix, even a corrected `tags.Name` default produces empty columns).

  Two surgical changes in src/awsquery/formatters.py:

  1. _is_aws_tags_structure(value) at line 195 - case-insensitive Key/Value membership check:

         def _is_aws_tags_structure(value):
             if not (isinstance(value, list) and value and isinstance(value[0], dict)):
                 return False
             lower_keys = {k.lower() for k in value[0].keys() if isinstance(k, str)}
             return 'key' in lower_keys and 'value' in lower_keys

  2. _transform_aws_tags_list(tags_list) at line 183 - resolve the actual key names case-insensitively per tag dict:

         def _transform_aws_tags_list(tags_list):
             tag_map = {}
             for tag in tags_list:
                 if not isinstance(tag, dict):
                     continue
                 key_name = next((k for k in tag if isinstance(k, str) and k.lower() == 'key'), None)
                 value_name = next((k for k in tag if isinstance(k, str) and k.lower() == 'value'), None)
                 if key_name is None or value_name is None:
                     continue
                 tag_key = tag[key_name]
                 if isinstance(tag_key, str) and tag_key.strip():
                     tag_map[tag_key] = tag[value_name]
             return tag_map

  Do NOT change transform_tags_structure itself - its `if key == "Tags"` branch matches the outer dict key (which is consistently capitalized across AWS shapes; lowercase-key issue is only in member names of the inner list dicts).

  Constraints:
  - Preserve existing behaviour for case-sensitive Key/Value (most AWS services). Tests for those must still pass.
  - Preserve the non-empty-key check (`tag_key and tag_key.strip()`) - existing tests assert this.
  - Per RESEARCH.md P5: do NOT introduce any extra special-case handling for nested Tags.Name - those already work and the executor must not gold-plate.

  Anti-patterns to avoid: do NOT rewrite the recursion in transform_tags_structure. Do NOT add a case-insensitivity flag - the change is unconditionally correct. Do NOT touch any other formatter function.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && python3 -m pytest tests/unit/test_tags_transformation.py tests/unit/test_formatters.py tests/unit/test_formatters_data_processing.py -v --no-cov && python3 -c "from awsquery.formatters import _is_aws_tags_structure, _transform_aws_tags_list; assert _is_aws_tags_structure([{'Key':'Name','Value':'web'}]); assert _is_aws_tags_structure([{'key':'Name','value':'web'}]); assert _is_aws_tags_structure([{'KEY':'Name','VALUE':'web'}]); assert not _is_aws_tags_structure([{'Name':'web'}]); assert _transform_aws_tags_list([{'key':'Name','value':'web'}]) == {'Name':'web'}; print('ok')"</automated>
  </verify>
  <done>
  - _is_aws_tags_structure returns True for tag dicts with Key/Value, key/value, KEY/VALUE, etc.
  - _transform_aws_tags_list correctly extracts Name -> web from lowercase-key tag dicts.
  - All existing tests in test_tags_transformation.py, test_formatters.py, and test_formatters_data_processing.py still pass.
  - Empty-key behaviour (skip tags whose key is empty/whitespace) is preserved.
  </done>
</task>

<task type="auto">
  <name>Task 5: Fix the 5 broken Tags-class entries in default_filters.yaml</name>
  <files>src/awsquery/default_filters.yaml</files>
  <action>
  MANDATORY: Delegate this implementation to @agent-python-infra-automator per CLAUDE.md. Provide the agent with the per-service classification table from RESEARCH.md (D4 decisions) and the exact line numbers below. Use the Edit tool surgically - these are seven line-level edits across four operations, no global rewrites.

  Edits (per RESEARCH.md, all 5 broken Tags-class entries + 2 leftovers):

  1. directconnect.describe_direct_connect_gateways (line 829): change `    - tags$` to `    - tags.Name`. NO `$` anchor - the directconnect shape uses lowercase `tags` as the outer key, and after the Task 4 transform fix, post-transform keys are `tags.Name`, `tags.Environment`, etc.; bare contains-match cleanly captures them.

  2. ec2.describe_vpcs (line 1071): change `    - Tags$` to `    - Tags.Name$`. K/V-tagged; post-transform `Tags.Name` is the standard human-readable label; suffix-anchor matches both top-level `Tags.Name` and nested instances per RESEARCH.md P5 - accepted as fine.

  3. ecr.describe_images (line 1087): change `    - imageTags$` to `    - imageTags`. NO `$` anchor - `imageTags` is a list-of-string, post-flatten becomes `imageTags.0`, `imageTags.1`, ...; substring/contains match captures all of them.

  4. redshift.describe_cluster_parameter_groups (lines 2230-2232): change `    - Tags$` (line 2230) to `    - Tags.Name$`, and DELETE both `    - Key$` (line 2231) and `    - Value$` (line 2232). The Tags.Name$ replacement makes the leftover Key$/Value$ redundant; per RESEARCH.md these are clearly an old attempt to surface K/V tag pairs.

  5. redshift.describe_cluster_security_groups (line 2241): change `    - Tags$` to `    - Tags.Name$`. K/V-tagged; same rationale as ec2.describe_vpcs.

  Do NOT touch any other `$`-suffix entries (RESEARCH.md confirms only these 5 entries - plus the 2 redshift leftovers - are in the in-scope Tags class). Do NOT restructure the YAML (CONTEXT.md D7). Do NOT change ec2.describe_instances (already uses Tags.Name per the existing defaults - verified). Do NOT touch ecr.list_images imageTag$ (the singular is correct - RESEARCH.md confirmed imageTag: string is the right shape).

  After edits, yaml.safe_load() the file and confirm:
  - cfg['directconnect']['describe_direct_connect_gateways']['columns'] contains 'tags.Name' (no $) and not 'tags$'.
  - cfg['ec2']['describe_vpcs']['columns'] contains 'Tags.Name$' and not 'Tags$'.
  - cfg['ecr']['describe_images']['columns'] contains 'imageTags' (no $) and not 'imageTags$'.
  - cfg['redshift']['describe_cluster_parameter_groups']['columns'] contains 'Tags.Name$' and does NOT contain 'Key$' or 'Value$'.
  - cfg['redshift']['describe_cluster_security_groups']['columns'] contains 'Tags.Name$' and not 'Tags$'.

  Constraint: line numbers may shift slightly after edits - anchor on the section header (`describe_direct_connect_gateways:`, `describe_vpcs:`, etc.) when applying each edit, not on absolute line numbers.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && python3 scripts/verify_yaml_fixes.py 2>/dev/null || python3 -c "
import yaml
cfg = yaml.safe_load(open('src/awsquery/default_filters.yaml'))
dc = cfg['directconnect']['describe_direct_connect_gateways']['columns']
vpcs = cfg['ec2']['describe_vpcs']['columns']
ecri = cfg['ecr']['describe_images']['columns']
rpg = cfg['redshift']['describe_cluster_parameter_groups']['columns']
rsg = cfg['redshift']['describe_cluster_security_groups']['columns']
assert 'tags.Name' in dc and 'tags' + chr(36) not in dc, ('directconnect', dc)
assert 'Tags.Name' + chr(36) in vpcs and 'Tags' + chr(36) not in vpcs, ('vpcs', vpcs)
assert 'imageTags' in ecri and 'imageTags' + chr(36) not in ecri, ('ecr.describe_images', ecri)
assert 'Tags.Name' + chr(36) in rpg and 'Tags' + chr(36) not in rpg and 'Key' + chr(36) not in rpg and 'Value' + chr(36) not in rpg, ('redshift.param', rpg)
assert 'Tags.Name' + chr(36) in rsg and 'Tags' + chr(36) not in rsg, ('redshift.sec', rsg)
print('all 5 fixes + 2 deletions confirmed')
" && python3 -m pytest tests/unit/test_default_column_filters.py -v --no-cov</automated>
  </verify>
  <done>
  - directconnect.describe_direct_connect_gateways uses `tags.Name` (no $).
  - ec2.describe_vpcs uses `Tags.Name$`.
  - ecr.describe_images uses `imageTags` (no $).
  - redshift.describe_cluster_parameter_groups uses `Tags.Name$`, with `Key$` and `Value$` deleted.
  - redshift.describe_cluster_security_groups uses `Tags.Name$`.
  - YAML still parses cleanly. All existing tests still pass.
  </done>
</task>

<task type="auto">
  <name>Task 6: Add scripts/audit_default_filters.py for shape-aware regression detection</name>
  <files>scripts/audit_default_filters.py</files>
  <action>
  MANDATORY: Delegate this implementation to @agent-python-infra-automator per CLAUDE.md.

  Create scripts/audit_default_filters.py based on the 90-LOC prototype embedded in research/codebase.md (under "Audit prototype (drop-in reference, 90 LOC)"). Port that prototype as-is with the following adjustments:

  1. Module docstring (one paragraph): "Static shape-aware audit of default_filters.yaml. Walks every $-suffix entry, looks up the service+operation shape via ShapeCache, simulates the same flattening the formatter applies (transform_tags_structure + flatten_dict_keys), and classifies each entry as correct, broken, kv_dyn, wildcard, or unverified. Returns a dict suitable for CI regression checks."

  2. Function signature: `def audit_default_filters(config_path: str = None) -> dict` - default to the package's default_filters.yaml (resolve via `os.path.join(os.path.dirname(awsquery.__file__), 'default_filters.yaml')`).

  3. Apply the known-false-positive exemption from RESEARCH.md / codebase.md: when the top-level data field for the operation is a list-of-primitive and base.lower() == 'value', classify as CORRECT (this avoids flagging working defaults like `ecs.list_clusters value$`).

  4. CLI entry point (`if __name__ == '__main__':`) that prints counts and broken entries in human-readable form.

  5. NO new external dependencies beyond what's already in pyproject.toml (`boto3`, `PyYAML`).

  6. Reuse ShapeCache from src/awsquery/shapes.py exactly - do NOT extend it.

  Anti-patterns to avoid:
  - Do NOT hard-gate CI on "broken count == 0" in this task. The audit has documented false-positives (RESEARCH.md P6); the test in Task 7 instead asserts that a TARGETED set of historically-broken entries (the ones Task 5 fixes) no longer appears in `broken`.
  - Do NOT bundle the prototype with shell scripts or Makefile changes - this is a single-purpose Python script.
  - Do NOT copy transform_tags_structure into the audit - the heuristic is shape-aware static detection; the runtime transform is the simulation target, not a code dependency.

  After writing, run `python3 scripts/audit_default_filters.py` once and confirm:
  - It prints counts in the format `Broken: N, Correct: M, ...`.
  - None of the 5 in-scope broken entries (directconnect tags$, ec2 vpcs Tags$, ecr describe_images imageTags$, redshift param-groups Tags$, redshift sec-groups Tags$) appear in the broken list - because Task 5 fixed them.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && python3 scripts/audit_default_filters.py | head -30 && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from audit_default_filters import audit_default_filters
r = audit_default_filters()
broken_keys = {(svc, op) for svc, op, *_ in r['broken']}
fixed = [('directconnect','describe_direct_connect_gateways'), ('ec2','describe_vpcs'), ('ecr','describe_images'), ('redshift','describe_cluster_parameter_groups'), ('redshift','describe_cluster_security_groups')]
for svc, op in fixed:
    assert (svc, op) not in broken_keys, f'still broken: {svc}.{op}'
print('audit confirms targeted fixes')
"</automated>
  </verify>
  <done>
  - scripts/audit_default_filters.py exists and is executable as a script.
  - `python3 scripts/audit_default_filters.py` runs without error and prints a count summary.
  - `audit_default_filters()` is importable and returns a dict with keys broken, correct, wildcard, kv_dyn, unverified.
  - None of the 5 in-scope historically-broken (service, operation) pairs appear in the broken list after Task 5's edits.
  - No new external dependencies introduced.
  </done>
</task>

<task type="auto">
  <name>Task 7: Add tests for additive merge, + parsing, directconnect tags, and audit cleanliness</name>
  <files>tests/unit/test_default_column_filters.py, tests/unit/test_tags_transformation.py, tests/unit/test_cli_parser.py, tests/unit/test_filter_validator.py</files>
  <action>
  MANDATORY: Delegate ALL test creation to @agent-test-writer per CLAUDE.md "Test Development - MANDATORY @agent-test-writer Usage". Do NOT write tests inline. Provide the agent with this PLAN, the existing test patterns from tests/unit/test_default_column_filters.py:107-205, and the strict CLAUDE.md test-quality rules (no pytest markers except parametrize, no verbose docstrings, real implementation over mocks, mock only boto3/file I/O).

  Add tests, organized by existing file home (CLAUDE.md "Consolidate Related Tests"):

  1. tests/unit/test_default_column_filters.py - extend with new test classes (do NOT create a new file):

     TestApplyDefaultFiltersAdditive:
     - test_additive_true_merges_defaults_and_user_columns: assert defaults appear first, then user.
     - test_additive_true_dedup_case_sensitive: `+Foo` + default `Foo` -> single entry; `+foo` + default `Foo` -> both kept (CONTEXT.md D2).
     - test_additive_true_empty_user_returns_defaults
     - test_additive_true_no_defaults_returns_user_columns
     - test_additive_false_behaviour_unchanged: regression test for today's path.
     - test_additive_preserves_order: defaults order preserved, then user CLI order.

     TestDetermineColumnFiltersAdditive (extends existing TestDetermineColumnFilters):
     - test_plus_prefix_triggers_additive_mode: pass `['+Foo']`; assert defaults + Foo with `+` stripped.
     - test_mixed_plus_and_bare_triggers_additive: `['Bar', '+Foo']` -> defaults + Bar + Foo per CONTEXT.md D1.
     - test_multiple_plus_columns: `['+A', '+B']` -> defaults + A + B.
     - test_bare_only_replaces_defaults: `['Foo']` (no +) -> today's behaviour.
     - test_additive_stderr_echo_renders_plus: capture stderr, assert "Using default columns + additions:" present and the user-added entries render with `+` prefix (copy-paste-runnable).
     - test_additive_no_validator_warnings_for_tag_columns: capture stderr, assert no "WARNING: Some column filters may not match" line for `+Tags.Name` (the validator's `'tag' in filter.lower()` short-circuit must fire on the STRIPPED token).
     - test_additive_falls_back_to_user_when_no_defaults: unknown service+action -> still returns user columns sans `+`.

  2. tests/unit/test_tags_transformation.py - extend with lowercase-key fixtures:

     - test_is_aws_tags_structure_accepts_lowercase_key_value: `[{'key':'Name','value':'web'}]` -> True.
     - test_is_aws_tags_structure_accepts_mixed_case: `[{'KEY':'X','Value':'y'}]` -> True.
     - test_is_aws_tags_structure_rejects_missing_key_or_value: still False.
     - test_transform_aws_tags_list_handles_lowercase: `[{'key':'Name','value':'web'}]` -> `{'Name':'web'}`.
     - test_transform_tags_structure_directconnect_simulated: a top-level dict like `{'tags': [{'key':'Name','value':'gw1'}]}` (note: outer key 'tags' lowercase - simulate how the runtime presents directconnect responses) - assert after transform + flatten the key `tags.Name -> gw1` exists. Hint: the recursion in transform_tags_structure matches the OUTER key `Tags` (capital). For directconnect, the executor must verify whether the outer key is `Tags` or `tags` in real responses - the test fixture documents the expected runtime shape.

  3. tests/unit/test_cli_parser.py (or test_cli_flags.py - existing file) - regression:

     - test_plus_prefixed_positional_parses_cleanly: assert argparse + _process_remaining_args + _build_filter_argv + parse_multi_level_filters_for_mode preserve `+Foo` through to the column-filters list.
     - test_plus_prefix_with_value_filter_separator: `awsquery ec2 describe-instances Bar -- +Foo` -> resource filters [Bar], column filters [+Foo].
     - test_plus_prefix_does_not_affect_value_filters: `awsquery ec2 describe-instances +Bar -- Foo` -> behaviour per D3: only column-filter group gets additive treatment.

  4. tests/unit/test_filter_validator.py (existing) - one regression:

     - test_plus_prefixed_columns_not_warned_for: the validator should never receive `+`-prefixed tokens (Task 2 strips them upstream); add a test that calls validate_columns directly with `+Foo` and asserts the behaviour is unchanged from `Foo` (this documents the contract; the strip is in the caller).

  5. NEW test file ONLY IF NEEDED for the audit: tests/unit/test_default_filters_audit.py - if and only if no existing test file covers `scripts/`. The test:

     - test_audit_no_in_scope_broken_entries: import `audit_default_filters` from scripts; assert none of the 5 historically-broken (service, operation) pairs appear in the `broken` list after Task 5's YAML edits. Use a fixed allowlist of expected (service, operation) pairs and assert the audit result excludes them.

     If `tests/unit/test_default_column_filters.py` already contains a class like TestYAMLConfigurationStructure (it does, line 205), prefer ADDING the audit test there as a new method `test_audit_clean_for_in_scope_fixes`. Avoid creating a new file unless necessary.

  Constraints (CLAUDE.md):
  - NO @pytest.mark.* decorators except parametrize.
  - NO verbose test docstrings.
  - Mock only external dependencies (boto3.client, file I/O). Test the real apply_default_filters, determine_column_filters, _is_aws_tags_structure, _transform_aws_tags_list.
  - Edge cases REQUIRED: empty list, None, Unicode, malformed input where applicable.
  - For directconnect fixture: stub the boto3 response with a lowercase `tags` outer key AND lowercase `key`/`value` members (verify the executor's interpretation of the directconnect response shape - the test fixture should match the actual botocore shape).
  - Use existing fixtures from tests/conftest.py and tests/fixtures/.
  - Do NOT add duplicate test files. Reuse the homes listed above.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && python3 -m pytest tests/unit/test_default_column_filters.py tests/unit/test_tags_transformation.py tests/unit/test_cli_parser.py tests/unit/test_cli_flags.py tests/unit/test_filter_validator.py -v --no-cov 2>&1 | tail -50 && grep -r "@pytest.mark" tests/unit/test_default_column_filters.py tests/unit/test_tags_transformation.py tests/unit/test_cli_parser.py tests/unit/test_cli_flags.py tests/unit/test_filter_validator.py | grep -v parametrize && echo NO_FORBIDDEN_MARKERS || echo CHECK_FAILED</automated>
  </verify>
  <done>
  - New TestApplyDefaultFiltersAdditive and TestDetermineColumnFiltersAdditive classes exist in test_default_column_filters.py with all cases listed above.
  - test_tags_transformation.py covers lowercase-key Key/Value fixtures.
  - test_cli_parser.py or test_cli_flags.py asserts `+Foo` parses cleanly end-to-end.
  - Audit-clean assertion exists (either as a new file or - preferred - as a method on TestYAMLConfigurationStructure).
  - No pytest markers other than parametrize anywhere in modified test files.
  - All new tests pass; no existing tests broken.
  </done>
</task>

<task type="auto">
  <name>Task 8: Document +Column syntax in README</name>
  <files>README.md</files>
  <action>
  Extend the README's filter documentation to describe the new `+Column` prefix. NO mandatory agent for docs-only changes (Python agent is mandated for Python code; this is markdown). The executor may edit directly.

  Target sections (verified line numbers from current README.md):
  - `## Configuration` -> `### Default Filters Configuration` (line 293) - add a one-sentence pointer mentioning `+Column` additive override.
  - `## Advanced Usage` -> `### Filter Matching Behavior` -> `#### Column Filters (after \`--\`)` (line 430) - the primary documentation site.

  Add a new sub-section under #### Column Filters titled `**Additive Column Filters (`+Column`)**` with this body (verbatim, plain markdown):

      By default, supplying any column filter REPLACES the curated defaults from `default_filters.yaml`.
      Prefix any column with `+` to merge with the defaults instead:

      | Command                                                | Columns shown                                             |
      | :----------------------------------------------------- | :-------------------------------------------------------- |
      | `awsquery ec2 describe-instances`                      | `default_filters.yaml` defaults                           |
      | `awsquery ec2 describe-instances -- InstanceId`        | only `InstanceId` (replaces defaults)                     |
      | `awsquery ec2 describe-instances -- +InstanceId`       | defaults + `InstanceId` (merged, deduped, defaults first) |
      | `awsquery ec2 describe-instances -- InstanceId +OwnerId` | defaults + `InstanceId` + `OwnerId` (any `+` triggers additive mode for the whole column-filter group) |

      Notes:
      - `+` is recognised anywhere in the column-filter group (after the `--` separator).
      - Order is `defaults` first, then your `+`-prefixed and bare columns in CLI order.
      - Dedup is case-sensitive on the exact pattern string: `+Foo` + default `Foo` collapses to one column; `+foo` + `Foo` keeps both.
      - `+` applies only to column filters - value/resource filter behaviour is unchanged.

  Do NOT touch the existing filter-operator table or value-filter documentation. Do NOT mention the deferred ideas (`-Column`, `--additive` flag).

  Constraint: the README is the user-facing surface. Per CLAUDE.md "CLI commands must remain stable", this is a NEW capability being documented - it does NOT contradict any existing behaviour described in the README.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && grep -n "Additive Column Filters\|+Column\|+InstanceId" README.md && python3 -c "
content = open('README.md').read()
assert '+Column' in content or '+InstanceId' in content or 'Additive Column Filters' in content
assert 'defaults first' in content.lower() or 'defaults +' in content
print('README documents +Column syntax')
"</automated>
  </verify>
  <done>
  - README.md has a new sub-section documenting `+Column` under `#### Column Filters (after \`--\`)`.
  - The truth table from CONTEXT.md D1 is reflected in the docs.
  - The default-filters config section points to the new syntax.
  - No removed/changed content outside the new sub-section.
  </done>
</task>

<task type="auto">
  <name>Task 9: Run @agent-code-reviewer on all changes</name>
  <files>(no file edits; review-only)</files>
  <action>
  MANDATORY per CLAUDE.md "Code Review - MANDATORY @agent-code-reviewer Usage": invoke @agent-code-reviewer over the cumulative diff of Tasks 1-8. This is a proactive, automatic agent invocation that CLAUDE.md mandates after significant code changes.

  Provide the reviewer with:
  - The cumulative diff: `git diff main...HEAD` from the worktree.
  - The locked CONTEXT.md decisions (D1-D7).
  - The RESEARCH.md pitfalls list (P1-P8).
  - The CLAUDE.md mandatory rules (no pytest markers, no verbose test docstrings, real-impl tests).

  The reviewer must check:
  - apply_default_filters and determine_column_filters preserve today's behaviour when no `+` is present (regression risk).
  - `+` strip happens BEFORE FilterValidator.validate_columns (else stderr warnings fire - RESEARCH.md P2).
  - _is_aws_tags_structure case-insensitivity does NOT change behaviour for canonical Key/Value services.
  - YAML edits touched ONLY the 5 in-scope entries + 2 leftovers; nothing else changed.
  - Audit script is reusable, has no hard-coded paths beyond `default_filters.yaml`, and does not introduce new dependencies.
  - Tests cover the truth table from CONTEXT.md D1 line-for-line.
  - No backward-compat shims, no deprecation warnings (CLAUDE.md philosophy).
  - Commit messages are single-line and meet CLAUDE.md format.

  If the reviewer surfaces material issues, address them in new commits (do NOT amend). If the reviewer surfaces stylistic-only concerns, document but defer.

  Output: the reviewer's verdict (pass/fail-with-fixes), captured in EXECUTION.md.
  </action>
  <verify>
  <automated>cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax && make test 2>&1 | tail -40 && make lint 2>&1 | tail -20 && echo "Code review prompt sent to @agent-code-reviewer; verdict captured in EXECUTION.md"</automated>
  </verify>
  <done>
  - @agent-code-reviewer invoked with the full cumulative diff.
  - Reviewer's verdict captured in EXECUTION.md (pass, or fail with follow-up commits).
  - `make test` passes (all unit + integration tests green).
  - `make lint` passes (flake8 + pylint clean).
  - No new linting violations introduced.
  </done>
</task>

</tasks>

<verification>
After all 9 tasks, run final checks from the worktree:

    cd /workspace/.worktrees/sue5t-fix-tags-default-filters-and-add-additive-column-syntax
    make test         # full test suite (unit + integration), directory-based discovery
    make lint         # flake8 + pylint
    make format-check # black + isort verification
    make type-check   # mypy
    python3 scripts/audit_default_filters.py   # confirms broken count for in-scope entries is 0

End-to-end smoke (optional but recommended for the executor; requires AWS creds if not mocked):

    awsquery ec2 describe-vpcs --debug 2>&1 | head -5
      # stderr should show: "Using default columns: -- Tags.Name$ VpcId$ ..."
    awsquery ec2 describe-vpcs -- +OwnerId --debug 2>&1 | head -5
      # stderr should show: "Using default columns + additions: -- Tags.Name$ VpcId$ ... +OwnerId"

</verification>

<success_criteria>
Maps 1:1 to ISSUE.md acceptance criteria:

- [x] Walk every $-suffix entry in default_filters.yaml; classify and fix all that anchor against post-transformation-invisible keys.
  -> Task 5 (5 fixes + 2 deletions) and Task 6 (audit script + regression test).

- [x] `awsquery ec2 describe-instances` and `awsquery ec2 describe-vpcs` show the `Name` tag populated by default.
  -> Task 5 fixes describe_vpcs; describe_instances already uses Tags.Name (verified in research). Task 7 includes a regression test asserting Tags.Name is in the defaults for both.

- [x] `+Column` CLI syntax merges with defaults (dedup + order-preserving); bare `Column` still replaces defaults.
  -> Tasks 1 + 2 implement the merge; Task 7 covers the truth table from CONTEXT.md D1.

- [x] Multiple `+`-prefixed columns work in the same invocation.
  -> Task 2 detects "any `+`-prefixed"; Task 7 has test_multiple_plus_columns and test_mixed_plus_and_bare_triggers_additive.

- [x] Unit + integration tests cover both the corrected defaults and the additive-merge logic.
  -> Task 7 in test_default_column_filters.py, test_tags_transformation.py, test_cli_parser.py, test_filter_validator.py.

- [x] Research phase uses graphify (per request) and the resulting RESEARCH.md notes whether it was actually useful.
  -> Completed pre-plan in RESEARCH.md "Graphify usefulness" section. Verdict: worth integrating via JSON traversal; CLI query/explain are noisy.

- [x] README's filter section documents `+Column`.
  -> Task 8.

- [x] Post-fix audit pass confirms no regressions and no remaining broken $-suffix defaults.
  -> Task 6 audit script; Task 7 audit-clean assertion against the in-scope set.

- [x] _is_aws_tags_structure handles lowercase Key/Value (companion fix unblocking directconnect, per RESEARCH.md P1).
  -> Task 4.

- [x] `+` columns echoed to stderr render with their `+` prefix so the echoed command is copy-paste-runnable (RESEARCH.md open question resolved).
  -> Task 3 extends _format_columns_copyable; Task 2 calls it with additive_marks.
</success_criteria>
