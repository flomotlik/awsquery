# CONTEXT — ty5dx

Design decisions captured before research/planning. The researcher and planner
must treat the "Decisions" section as locked.

## Decisions (locked — research/planner must follow)

- **Config location: a new `src/awsquery/default_actions.yaml`**, flat
  `service: action` map (`ec2: describe_instances`). Not a key inside
  `default_filters.yaml`.
  **Why:** two walkers assume the strict `service -> action -> {columns: [...]}`
  shape — `scripts/audit_default_filters.py:71` (`opcfg.get("columns", [])`) and
  `tests/unit/test_default_column_filters.py:353`. A sibling string key would
  raise `AttributeError: 'str' object has no attribute 'get'` in both. A separate
  file leaves every existing walker untouched.
  Must be added to the package data list in `pyproject.toml:82` alongside
  `policy.json` and `default_filters.yaml`, or it will not ship in the wheel.

- **Loader mirrors the existing config module.** Add `load_default_actions()`
  (`@lru_cache(maxsize=1)`, same FileNotFoundError / YAMLError / generic
  fallbacks returning `{}`) and `get_default_action(service)` to
  `src/awsquery/config.py`, shaped exactly like `load_default_filters()` /
  `get_default_columns()`: lowercased lookup, `debug_print` on both hit and
  miss, `None` when unset.

- **Action names only — no default parameters.** The map value is the operation
  name and nothing else. Output shaping stays with `default_filters.yaml`
  columns.

- **Defaults are restricted to operations with no required parameters.** A
  service whose natural listing needs an argument (e.g. `logs
  describe-log-streams` needs `LogGroupName`) gets no default at all rather
  than a default that fans out. `awsquery <service>` must always be a single
  immediate call — no multi-level parameter resolution triggered by a default.

- **Coverage: broad sweep (~50+ services).** Cover every service already in
  `default_filters.yaml` that has an obvious parameterless list/describe entry
  point. Skip any service where the entry point needs parameters (per the rule
  above) or where no single operation is clearly "the" default.

- **Announcement: debug only.** A `debug_print` records which default was
  chosen. No hint on stderr during normal runs — stdout and stderr stay clean
  for piping.

- **Fallback when a service has no default:** print that service's available
  actions to stderr, exit non-zero. `awsquery` with no service at all keeps
  today's behavior (list services on stdout, exit 0).

- **Resolved action takes the normal code path.** Once substituted it flows
  through `validate_readonly`, default column filters, and any user `--`
  filters/flags unchanged. `awsquery ec2 -- InstanceId` must equal
  `awsquery ec2 describe-instances -- InstanceId`.

## Claude's Discretion (research should explore options)

- Exact insertion point in `main()` for the substitution — the current dead end
  is the `if not args.service or not args.action` branch at
  `src/awsquery/cli.py:830`, but `_build_filter_argv` (`cli.py:303`) also
  branches on `args.action` and may need the resolved value.
- Whether the fallback action listing reuses `get_service_operations()` /
  `get_service_valid_operations()` (already in `cli.py`, used by
  `action_completer`) or needs a shared helper.
- Naming: `get_default_action` vs. something clearer; the surrounding module
  favours `get_default_*`.
- How the curated map is validated: a test asserting every entry is a real
  botocore operation, is ReadOnly per `policy.json`, and has no required
  parameters is the obvious guard — shape and location are the researcher's
  call.
- Whether kebab-case (`describe-instances`) or snake_case
  (`describe_instances`) is the canonical value in the YAML;
  `normalize_action_name` (`utils.py`) already exists for conversion.

## Deferred (out of scope for this issue)

- Botocore heuristic inference for services with no curated entry — curated map
  only in this issue.
- Default parameters (`MaxResults`, filters) attached to a default action.
- User-level override of the curated map (`~/.awsquery/` config).
- Refreshing the stale `.issues/MAP.md` (99 days old at time of writing).
