# Pitfalls research — sue5t

## Critical pitfalls

### P1 — directconnect uses lowercase `key`/`value` keys; `transform_tags_structure` won't fire

**What goes wrong:** Replacing `tags$` with `tags.Name` in `directconnect describe_direct_connect_gateways` will still produce empty Name columns, because `_is_aws_tags_structure` (formatters.py:195) requires LITERAL `"Key"` and `"Value"` member names (case-sensitive). The directconnect service uses lowercase `key`/`value`, so the transform doesn't activate, and `Tags.Name` never materializes in the flattened output.

**Why it happens:** `_is_aws_tags_structure` does `"Key" in value[0] and "Value" in value[0]` — a strict membership check. Botocore's service model for directconnect literally uses lowercase shape members; live `ShapeCache.get_response_fields('directconnect', 'describe-direct-connect-gateways')` returns `tags.key` and `tags.value` (lowercase).

**How to avoid:**
- **Option A (recommended):** patch `_is_aws_tags_structure` and `_transform_aws_tags_list` to accept case-insensitive `Key`/`Value` member names. One-line fix per helper.
- **Option B:** skip the substitution for directconnect; document the limitation in default_filters.yaml comments. (Worse — user-visible inconsistency.)
- **Option C:** leave the existing `tags$` and add a substring filter like `tags.key` or `tags.value` instead. (Surfaces all key/value pairs, very noisy.)

The plan should opt for A. Tests already cover Tag transformation in `tests/unit/test_tags_transformation.py` — extend them with a lowercase fixture.

**Warning signs:** running `awsquery directconnect describe-direct-connect-gateways` after the fix and seeing empty Name columns. Add an integration smoke test against a stubbed lowercase-tag response.

### P2 — `FilterValidator` warns about `+`-prefixed columns if it sees them raw

**What goes wrong:** The `_validate_single_column` (filter_validator.py:85) short-circuits on `"tag" in column_filter.lower()`. So `+Tags.Name` passes — but `+InstanceId` would NOT short-circuit, and `parse_filter_pattern("+InstanceId")` returns `('+InstanceId', 'contains')`. The validator then asks "does any field contain `+InstanceId`?" → no → it prints `WARNING: Some column filters may not match response fields`. False alarm on every additive invocation.

**Why it happens:** `+`-stripping must happen BEFORE `FilterValidator.validate_columns` is invoked. The current call chain (cli.py:380-394) runs validation AFTER `determine_column_filters` resolves to `column_filters_to_use` — perfect spot to strip.

**How to avoid:** Strip the leading `+` from every user-supplied column before passing to `apply_default_filters` AND before the validator. Two clean strategies:
- Strip at the very top of `determine_column_filters` — recommended; minimal blast radius.
- Strip in a new helper `cli.partition_column_args(cols) -> (additive: bool, stripped: list[str])` invoked from `main()`. Slightly more refactor.

**Warning signs:** the validation warning printed for any `+Foo` input. Test by running `awsquery ec2 describe-instances +InstanceId` after the fix and asserting no warning fires (stderr must be clean for valid columns).

### P3 — Order-preserving dedup with Python `set()` will silently scramble order

**What goes wrong:** Naïve dedup using `list(set(defaults + user_cols))` would lose the deterministic ordering required by CONTEXT.md D2. Tests that assert column order would flake or pass under wrong assumption.

**Why it happens:** `set()` has no guaranteed iteration order. (CPython has implementation details but the language spec doesn't guarantee them.)

**How to avoid:** Use `list(dict.fromkeys(defaults + stripped_user_cols))`. `dict` order is part of the Python 3.7+ language spec; project requires 3.10+ (pyproject.toml).

**Warning signs:** test failures only on some Python versions, or intermittent. Pin the merge function to `dict.fromkeys` and assert exact column order in unit tests.

### P4 — Case-sensitive dedup loses near-duplicates that are runtime-equivalent

**What goes wrong:** CONTEXT.md D2 mandates case-sensitive dedup. But `matches_pattern` is case-INSENSITIVE at runtime. So `+InstanceId` + default `instanceid$` would be deduped to TWO entries; both match at runtime, producing duplicate columns in the output.

**Why it happens:** The dedup operates on the raw pattern strings; the runtime matcher operates on lowercased keys. The mismatch creates apparent-duplicate columns.

**How to avoid:** Accept the redundancy. CONTEXT.md D2 says "the worst case is a redundant column, which the column-width fitter handles gracefully." Document this in plan/release notes. Do NOT switch to case-insensitive dedup without going back to D2.

**Warning signs:** double-rendered columns in the output. Snapshot test against a fixed shape to catch regressions.

### P5 — `Tags.Name$` and `ec2.describe_vpcs` interaction with `EncryptionControl.Tags`

**What goes wrong:** The shape for `ec2.describe-vpcs` includes BOTH `Tags` (top-level VPC tags) AND `EncryptionControl.Tags` (nested encryption metadata). Replacing `Tags$` with `Tags.Name$` (suffix-anchor) will match BOTH `Vpcs.Tags.Name` AND `Vpcs.EncryptionControl.Tags.Name` if either has a `Name` tag. That's probably desirable but may surface unexpected columns.

**Why it happens:** Suffix anchors are non-specific by design. The deeper `EncryptionControl.Tags` rarely has a `Name` tag in practice, so the noise is low — but it CAN show up.

**How to avoid:**
- Use the exact-anchor `^Tags.Name$` if the top-level binding matters. Slight risk: `transform_tags_structure` is recursive and produces `Tags.Name` keys at every nesting level — exact anchor only matches the path the user typed.
- For now, the suffix `Tags.Name$` is the safer default — matches consistently across services. Accept the EncryptionControl side-channel.

**Warning signs:** `awsquery ec2 describe-vpcs` shows a "Name (+1 more)" cell in the Tags.Name column. The aggregation indicator already exists (`MAX_AGGREGATED_VALUES = 3`).

### P6 — Audit script false positives may slip into the planner's "fix list"

**What goes wrong:** The audit prototype (codebase.md) reports 33 broken entries. ~28 of those are `value$` against list-of-primitive top-level data fields, which are actually CORRECT (each item wraps to `{value: item}` after flatten). If the executor blindly "fixes" these, they'll break working defaults.

**Why it happens:** `flatten_dict_keys` (formatters.py:351) wraps non-dict input as `{'value': d}` (line 354) — but the audit operates on the static shape, where the same field appears as a list. Two different worlds.

**How to avoid:** The planner MUST add a top-level data-field-list-of-primitive exemption in the audit, or instruct the executor to manually review every "broken" entry before editing. The codebase.md prototype includes the note; the plan must echo it.

**Warning signs:** the audit report flags entries the executor doesn't recognize as user-reported broken. If something other than `tags$`/`Tags$`/`imageTags$` shows up as "must fix", treat with suspicion and validate against a live (or stubbed) response first.

### P7 — `ssm.get_parameters Parameters$` is a data-field name collision

**What goes wrong:** ssm `get_parameters` has `data_field=Parameters` (a list). `flatten_response` extracts the list, and each element flattens individually. So `Parameters$` (the literal data-field name) never appears as a key. Audit correctly flags it as broken — but it's a SEPARATE bug class from the Tag issue.

**Why it happens:** the default was probably added thinking `Parameters` would survive as a column. The data-field extraction strips it.

**How to avoid:** Out of scope for this issue. The user requested `Tags`/additive specifically. Document `ssm.get_parameters Parameters$` in the audit report and leave it to a follow-up issue. Do NOT scope-creep.

### P8 — argcomplete completion table doesn't include `+` entries

**What goes wrong:** Shell autocomplete for `awsquery ec2 describe-instances +<TAB>` won't suggest any columns, because `argcomplete` only completes against the registered completers (`service_completer`, `action_completer`). Column-filter args have no completer.

**Why it happens:** Today's CLI has no column-name autocomplete (column names depend on AWS response). Not changed by this issue.

**How to avoid:** Just document. Users type column names by hand. Defer column-name autocomplete to a future issue.

## Security concerns

None specific to this issue. The Tags fix and additive syntax don't touch security boundaries (policy.json, `validate_readonly`, etc.). The standard ReadOnly enforcement (security.py) continues to gate all API calls.

## Edge cases (must have test coverage)

| Case                                                        | Expected                                                  |
|-------------------------------------------------------------|-----------------------------------------------------------|
| `awsquery ec2 describe-instances` (no user cols)            | Defaults applied (today's behavior, unchanged)             |
| `awsquery ec2 describe-instances InstanceId State`          | Replaces defaults (today's behavior, unchanged)            |
| `awsquery ec2 describe-instances +InstanceId`               | Defaults + InstanceId, deduped                             |
| `awsquery ec2 describe-instances +InstanceId +State`        | Defaults + InstanceId + State                              |
| `awsquery ec2 describe-instances InstanceId +State`         | Defaults + InstanceId + State (mixed mode flips to additive)|
| `awsquery ec2 describe-instances +Tags.Name`                | Defaults + Tags.Name (deduped — defaults already include it) |
| `awsquery ec2 describe-instances +InstanceId +InstanceId`   | Defaults + InstanceId (deduped)                            |
| `awsquery ec2 describe-instances +`                         | Edge: `+` alone after sanitize. Should it strip to `""` and become a no-op? Recommend: treat as error, print warning. |
| `awsquery ec2 describe-instances ++Foo`                     | `++Foo` after strip-one-`+` becomes `+Foo` (still a literal that matches nothing). Recommend: strip only the first `+`, document behavior. |
| `awsquery nonexistent describe-instances +InstanceId`       | No defaults exist → additive mode degenerates to "user_cols only" (current bare-only behavior). Document. |
| `awsquery ec2 describe-instances +"Tag.Name with space"`    | Quoted columns with spaces: pass through `sanitize_input`. Verify no surprise. |
| `awsquery directconnect describe-direct-connect-gateways`   | After P1 fix: Tags.Name populated. Before fix: empty (regression baseline). |
| Multi-level call with `-i` hint + `+Column`                 | Additive applies to FINAL column filter; resource/value filters unaffected (CONTEXT.md D3). |
| `awsquery ec2 describe-instances prod -- +InstanceId`       | Standard 1-separator: `prod` is value filter, `+InstanceId` is additive column. Verify routing. |
| `awsquery ec2 describe-instances -- prod -- +InstanceId`    | Standard 2-separator (multi mode): same partitioning. |

## Environment availability

| Dependency              | Required by                  | Available locally? | Version                  | Fallback                |
|-------------------------|------------------------------|--------------------|--------------------------|-------------------------|
| Python                  | All                          | yes                | 3.10+ (pyproject baseline) | n/a                     |
| pytest                  | Tests                        | yes                | ≥7.0                     | n/a                     |
| boto3                   | ShapeCache, audit            | yes                | 1.43.18 (verified live)  | n/a                     |
| moto                    | Integration tests with AWS mocks | yes (test dep)  | (per pyproject)          | n/a                     |
| PyYAML                  | default_filters.yaml + audit | yes                | ≥6.0                     | n/a                     |
| argcomplete             | CLI                          | yes                | 3.6.3 (verified)         | n/a                     |
| tabulate                | Table output                 | yes                | 0.10.0                   | n/a                     |
| graphify CLI            | RESEARCH (this issue)        | yes                | (verified, see graphify usefulness section in RESEARCH.md) | grep + Read fallback |
| pre-built graph.json    | RESEARCH                     | yes                | `/workspace/graphify-out/graph.json` (3,616 nodes, 5,217 edges) | re-build via `graphify update /workspace` |

## Sources

### HIGH confidence
- Live experimentation with `argparse`, `parse_filter_pattern`, `_process_remaining_args` (in this worktree's venv)
- Live shape introspection via `ShapeCache.get_response_fields` for ec2, ecr, redshift, sns, sqs, directconnect, ssm
- `default_filters.yaml` raw inspection (1,961 `$`-suffix entries enumerated)
- Audit prototype (33 candidate-broken across 1,861 audited entries)
- `formatters.py:_is_aws_tags_structure` source verification for case-sensitivity issue

### MEDIUM confidence
- Behavior of `transform_tags_structure` on lowercase `key`/`value` directconnect responses — derived from reading source + shape, not from a live `awsquery directconnect describe-direct-connect-gateways` invocation against real AWS. Recommendation: add an integration test with a stubbed response before merging.

### LOW confidence
- (none — every claim verifiable in this worktree)
