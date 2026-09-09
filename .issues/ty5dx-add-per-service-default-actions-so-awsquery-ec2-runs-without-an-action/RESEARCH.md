# Research: Add per-service default actions so `awsquery ec2` runs without an action

**Researched:** 2026-09-08
**Issue:** ty5dx-add-per-service-default-actions-so-awsquery-ec2-runs-without-an-action
**Confidence:** HIGH (all load-bearing claims verified by execution against the real code + botocore 1.43.89)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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

### Claude's Discretion (this research resolves each)

- Exact insertion point in `main()` — **resolved: pre-parse argv injection**, see Q1.
- Whether the fallback reuses `get_service_operations()` / `get_service_valid_operations()` — **resolved: yes, verbatim reuse**, see Q6.
- Naming `get_default_action` — **resolved: keep it**, matches `get_default_columns`.
- How the curated map is validated — **resolved: one parametrized test over the whole map**, see Q5.
- kebab-case vs snake_case in the YAML — **resolved: kebab-case is MANDATORY**, see Q4. This is not a style preference; snake_case breaks `validate_readonly`.

### Deferred Ideas (OUT OF SCOPE)

- Botocore heuristic inference for services with no curated entry.
- Default parameters (`MaxResults`, filters) attached to a default action.
- User-level override of the curated map (`~/.awsquery/`).
- Refreshing the stale `.issues/MAP.md`.
</user_constraints>

## Summary

The issue frames the change as "when `args.action` is empty, substitute the default." **That framing is wrong and will silently fail one of the acceptance criteria.** `service` and `action` are both `nargs="?"` positionals, so argparse consumes the `--` separator and assigns the *first column filter* to `action`: `awsquery ec2 -- InstanceId` parses to `service='ec2', action='InstanceId', remaining=[]` — byte-identical to `awsquery ec2 InstanceId`. Post-parse, the two are indistinguishable. Any substitution keyed on `args.action is None` therefore leaves `awsquery ec2 -- InstanceId` running a bogus operation named `InstanceId`, exactly as it does today.

The fix that works is **pre-parse argv injection**: a small pure function scans the raw token list, finds the first non-flag token (honouring `VALUE_FLAGS` consuming a following value), and — if the next token is absent, is `--`, or starts with `-` — splices the configured default action in right after the service. Everything downstream (`_build_filter_argv`, the two-pass reorder, `parse_multi_level_filters_for_mode`, `validate_readonly`, `check_parameter_requirements`, `determine_column_filters`) then sees exactly the argv the user "would have typed", so the acceptance criteria become true *by construction* rather than by parallel code paths. I simulated the real parsing pipeline over 11 command shapes (flags before and after the service, `-p` with a value, `--region`, double separators, trailing `--`) and every bare form produced a parse state identical to its explicit counterpart.

The second load-bearing finding is casing. `security.is_readonly_operation()` only PascalCases its input when the string contains a `-`; given `describe_instances` it compares `"describe_instances".startswith("Describe")` → `False`, falls through to `prompt_unsafe_operation()`, and **blocks on `input()` for stdin**. So a snake_case value in `default_actions.yaml` — the spelling the CONTEXT.md example shows — turns `awsquery ec2` into an interactive "may not be read-only" prompt. The YAML must hold kebab-case, with a defensive `to_kebab_case(to_snake_case(v))` normalisation at the injection boundary so either spelling is safe.

**Primary recommendation:** add `_inject_default_action(argv)` to `cli.py`, call it on `sys.argv[1:]` immediately after `argcomplete.autocomplete(...)` and pass the result to `parse_known_args()` (cli.py:752); store kebab-case in `src/awsquery/default_actions.yaml`; split the `cli.py:830` dead-end into a no-service branch (stdout, exit 0) and a no-default branch (stderr action list, exit 1); ship the 50-entry curated map below, every entry of which I verified is a real botocore operation with zero required members, ReadOnly by the project's own prefix rule, and already has curated columns in `default_filters.yaml`.

## Codebase Analysis

### Relevant Code

| File | Purpose | Relevance |
|------|---------|-----------|
| `src/awsquery/cli.py` | `main()`, arg reordering, `_build_filter_argv`, completers | **Primary change surface** — lines 237-239, 298-320, 632-666, 749-833 |
| `src/awsquery/config.py` | `load_default_filters()` / `get_default_columns()` / `apply_default_filters()` | Add `load_default_actions()` / `get_default_action()` here (86 lines today) |
| `src/awsquery/default_actions.yaml` | **NEW** flat `service: kebab-action` map | The curated data |
| `src/awsquery/security.py` | `is_readonly_operation()` prefix matcher, `get_service_valid_operations()` | Casing trap (Q4); reused by the fallback (Q6) |
| `src/awsquery/utils.py` | `get_service_operations()`, `normalize_action_name = to_snake_case` | Reused by the fallback |
| `src/awsquery/case_utils.py` | `to_snake_case` / `to_kebab_case` / `to_pascal_case` | Canonicalisation at the injection boundary |
| `src/awsquery/filters.py:136` | `parse_multi_level_filters_for_mode` | Consumes 2 leading non-flag tokens as service+action — hazard if action stays `None` |
| `src/awsquery/core.py:34` | `check_parameter_requirements` | The "required parameters" question (Q2) — but uses a live boto3 client |
| `src/awsquery/shapes.py` | `ShapeCache` via `botocore.loaders.Loader` | Credential-free model access — the right tool for the validation test (Q2) |
| `pyproject.toml:82` | `awsquery = ["policy.json", "default_filters.yaml"]` | Must gain `default_actions.yaml` |
| `scripts/audit_default_filters.py:71` | `opcfg.get("columns", [])` | Untouched, because the map lives in a separate file |

### Interfaces

<interfaces>
# ── src/awsquery/config.py (existing — the shape to mirror) ──────────────────
@lru_cache(maxsize=1)
def load_default_filters():                       # -> dict | {}  on any error
def get_default_columns(service, action):         # -> list[str]  ([] when unset)
def apply_default_filters(service, action, user_columns=None, additive=False)

# NEW, to be added — mirror shape exactly:
@lru_cache(maxsize=1)
def load_default_actions():                       # -> dict[str, str] | {}
def get_default_action(service):                  # -> str | None

# ── src/awsquery/cli.py (existing) ──────────────────────────────────────────
SIMPLE_FLAGS = ["-d", "--debug", "-j", "--json", "-k", "--keys", "--allow-unsafe"]   # line 237
VALUE_FLAGS  = ["--region", "--profile", "-p", "--parameter", "-i", "--input"]       # line 238

def _extract_flag_and_value(args, i)              # -> (list[str], int consumed)     line 247
def _process_remaining_args_after_separator(rem)  # -> (flags, non_flags)            line 258
def _process_remaining_args(remaining)            # -> (flags, non_flags)            line 278
def _build_filter_argv(args, remaining)           # -> list[str]                     line 298
def determine_column_filters(column_filters, service, action, json_output=False)     # line 340
def service_completer(prefix, parsed_args, **kwargs)                                 # line 241
def action_completer(prefix, parsed_args, **kwargs)                                  # line 632
def main()                                                                           # line 668

# NEW, to be added:
def _inject_default_action(argv)                  # -> list[str] (pure; never raises)
def _print_service_actions(service)               # -> None (writes stderr)

# ── src/awsquery/security.py ────────────────────────────────────────────────
SAFE_READONLY_PREFIXES = ["List","Get","Describe","BatchGet","BatchDescribe",
    "BatchCheck","BatchDetect","Search","Query","View","Lookup","Read","Scan",
    "Select","Check","Validate","Test","Preview","Verify","Estimate","Discover",
    "Retrieve","Has"]
def is_readonly_operation(action: str) -> bool
    # ⚠ ONLY PascalCases when "-" in action. snake_case input ALWAYS returns False.
def validate_readonly(service: str, action: str, allow_unsafe: bool = False) -> bool
    # falls through to prompt_unsafe_operation() -> blocking input() on stdin
def get_service_valid_operations(service: str, all_operations: list) -> set

# ── src/awsquery/utils.py ───────────────────────────────────────────────────
class _BotocoreSessionContext                 # ctx mgr; pops AWS_PROFILE, no creds needed
def get_aws_services() -> list[str]
def get_service_operations(service) -> list[str]   # PascalCase op names, [] if unknown
normalize_action_name = to_snake_case
pascal_to_kebab_case  = to_kebab_case
def debug_print(*args, **kwargs)                   # stderr, only when debug enabled

# ── src/awsquery/case_utils.py ──────────────────────────────────────────────
def to_snake_case(text: str) -> str    # verified == botocore.xform_name for all 50 picks
def to_pascal_case(text: str) -> str
def to_kebab_case(text: str) -> str

# ── src/awsquery/filters.py ─────────────────────────────────────────────────
def parse_multi_level_filters_for_mode(argv, mode="single")
    # -> (base_command, resource_filters, value_filters, column_filters)
    # Consumes the FIRST TWO non-flag tokens of segment 0 as service+action.

# ── src/awsquery/core.py ────────────────────────────────────────────────────
def check_parameter_requirements(service, action, provided_params, session=None) -> dict
    # {"needs_params": bool, "required": [...], "conditional": str|None,
    #  "missing_required": [...]}  — builds a live boto3 client; NOT test-safe.
def execute_aws_call(service, action, parameters=None, session=None)
    # getattr(client, normalize_action_name(action)) -> accepts kebab OR snake

# ── src/awsquery/shapes.py ──────────────────────────────────────────────────
class ShapeCache:
    def get_service_model(self, service) -> ServiceModel | None   # botocore Loader, no creds
    def get_operation_shape(self, service, operation)             # PascalCase + ci fallback
</interfaces>

### Reusable Components

- `get_service_operations(service)` (utils) + `get_service_valid_operations(service, ops)` (security) + `to_kebab_case` — **all three are already imported into `cli.py`** (lines 15, 33, 39). The fallback listing is a 6-line function with zero new imports; it is the same four-step sequence `action_completer` runs at cli.py:638-655.
- `botocore.loaders.Loader` via `shapes.ShapeCache` — credential-free service-model access for the map-validation test.
- `case_utils.to_kebab_case` / `to_snake_case` — verified to round-trip and to agree with `botocore.xform_name` for every acronym operation in the curated map (`ListSAMLProviders`, `ListMFADevices`, `DescribeSSLPolicies`, `DescribeDBInstances`, `ListVirtualMFADevices`, `ListAIWorkloadConfigs`).

### Potential Conflicts

| Location | Conflict | Resolution |
|----------|----------|------------|
| `tests/integration/test_end_to_end.py:889` `test_main_function_service_listing` | Uses `sys.argv = ["awsquery","ec2"]` and expects "Available services". After this change `awsquery ec2` runs `describe-instances` and will try to build a real client. The assertion is guarded by `if "Available services:" in output`, so it goes **vacuously green while actually attempting AWS** — a silent hang/credential-error risk in CI. | **Must be rewritten**, not left. Repoint it at a service with no default (e.g. `budgets`) and assert the stderr action listing + exit 1. |
| `tests/integration/test_end_to_end.py:629` `test_missing_service_action_edge_cases` | `["awsquery","","describe-instances"]` — empty service. Verified safe: the injector finds `""` as the service candidate, `get_default_action("")` returns `None`, no injection, `not args.service` still fires. | No change needed. |
| `tests/unit/test_default_column_filters.py:350,362` | `test_columns_are_strings` / `test_descriptions_not_required` call `action_config.get(...)` on every value of every service dict — a string sibling key would raise `AttributeError`. **This confirms the locked separate-file decision empirically.** | No change needed (separate file). |
| `scripts/audit_default_filters.py:71` | Same walker assumption. | No change needed (separate file). |
| `argcomplete.autocomplete()` at cli.py:749 | Runs before parsing and `exit()`s during completion. | Inject **after** this call, immediately before line 752. Injection must not mutate `sys.argv`. |
| cli.py:762 `has_separator = "--" in sys.argv` | Reads `sys.argv` directly, not the parsed argv. | Injection never adds or removes a `--`, so this stays correct. Verified in simulation. |

## The Seven Questions

### Q1 — Exact insertion point in `main()`

**Answer: before the first `parse_known_args()` (cli.py:752), operating on the raw token list. Nowhere else.**

The disqualifying evidence, produced by running the real parser configuration:

```
['ec2']                            -> service='ec2' action=None          remaining=[]
['ec2', '--', 'InstanceId']        -> service='ec2' action='InstanceId'  remaining=[]
['ec2', 'prod']                    -> service='ec2' action='prod'        remaining=[]
['ec2', '--', 'InstanceId','State']-> service='ec2' action='InstanceId'  remaining=['State']
```

argparse strips the first `--` and promotes the following token into the `action` positional. **`awsquery ec2 -- InstanceId` and `awsquery ec2 InstanceId` produce identical post-parse state.** No post-parse test — not on `args.action`, not on `remaining`, not on `has_separator` — can tell them apart. The information only exists in the raw token list.

Concretely, today `awsquery ec2 -- InstanceId State` ends up as `action='InstanceId'`, `column_filters=['State']` — it drops a column *and* invents an operation. Acceptance criterion "`awsquery ec2 -- InstanceId` == `awsquery ec2 describe-instances -- InstanceId`" is unreachable from a post-parse patch.

**Recommended shape:**

```python
def _inject_default_action(argv):
    """Splice the configured default action in after a bare service name."""
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            return argv
        if arg in VALUE_FLAGS:
            i += 2 if (i + 1 < len(argv) and not argv[i + 1].startswith("-")) else 1
            continue
        if arg.startswith("-"):
            i += 1
            continue
        break
    if i >= len(argv):
        return argv
    service = argv[i]
    following = argv[i + 1] if i + 1 < len(argv) else None
    if following is not None and following != "--" and not following.startswith("-"):
        return argv                      # user typed an explicit action
    action = get_default_action(service)
    if not action:
        return argv
    action = to_kebab_case(normalize_action_name(action))   # see Q4
    debug_print(f"Using default action for {service}: {action}")
    return argv[:i + 1] + [action] + argv[i + 1:]
```

Call site — replace cli.py:752:

```python
args, remaining = parser.parse_known_args(_inject_default_action(sys.argv[1:]))
```

**Ordering hazards, each checked:**

1. **`argcomplete.autocomplete()` (line 749) must run first.** It reads `COMP_LINE` and `exit()`s during shell completion. Injecting before it is harmless but pointless; injecting after keeps completion untouched. Put the call on line 752.
2. **Do not mutate `sys.argv`.** Line 762 (`has_separator = "--" in sys.argv`) and line 806 (`reordered_argv = [sys.argv[0]]`) both read it. Injection preserves the `--` count either way, but keeping `sys.argv` pristine means every existing test that assigns `sys.argv` still describes the user's real command.
3. **`_build_filter_argv` (line 298) needs no change** — it already emits `args.action` when truthy, and after injection it is always truthy for a defaulted service.
4. **The two-pass reorder (lines 755-815) needs no change** — it rebuilds `reordered_argv` from `args.service` / `args.action`, so the injected action survives the re-parse.
5. **`parse_multi_level_filters_for_mode` needs no change** — but note *why* it would break without injection: its segment-0 walker (filters.py:175-186) claims the first two non-flag tokens as service+action. With `action=None`, `filter_argv` is `['ec2', 'InstanceId', ...]` and `InstanceId` silently occupies the action slot instead of becoming a filter. Injection is what keeps that walker honest.
6. **`VALUE_FLAGS` scanning is required, not optional.** `awsquery --region us-west-2 ec2` must not mistake `us-west-2` for the service. `--region=us-west-2` (equals form) is not in `VALUE_FLAGS`, starts with `-`, and is correctly skipped as a single self-contained token.

**Verified equivalence.** I replayed the actual `parse_multi_level_filters_for_mode` source plus a faithful reimplementation of main()'s reorder pass over 11 command pairs. Every bare form produced a `(service, action, json, region, value_filters, column_filters)` tuple identical to its explicit counterpart:

```
OK  ec2                                 OK  -j ec2 -- InstanceId
OK  ec2 -- InstanceId                   OK  --region us-west-2 ec2
OK  ec2 -- InstanceId State             OK  ec2 -- -- InstanceId
OK  ec2 -j -- InstanceId                OK  s3 -- Name
OK  ec2 -j                              OK  ec2 -p MaxResults=5 -- InstanceId
OK  ec2 --
ALL EQUIVALENT: True
```

**Deliberately excluded: `awsquery ec2 prod`.** The injector treats any non-flag second token as an explicit action, so `ec2 prod` keeps today's behavior. The alternative — look the token up in `get_service_operations()` and demote it to a value filter if it is not an operation — was considered and rejected: a typo like `awsquery ec2 describe-instance` would then silently run `describe-instances` with a spurious value filter `describe-instance` and print zero rows, instead of erroring. It also costs a botocore service-model load on the hot path. Structural detection satisfies every acceptance criterion without that trap.

### Q2 — Determining required parameters programmatically

`core.check_parameter_requirements` (core.py:58-67) is the runtime answer, and it is the right one at runtime:

```python
client = get_client(service, session)
operation_model = client.meta.service_model.operation_model(normalize_action_name(action))
required = list(operation_model.input_shape.required_members)  # if input_shape
```

**But it is the wrong tool for the map-validation test**, because `get_client()` builds a live boto3 client — which needs a region and, for some services, credentials. Use the credential-free path that `shapes.py` already uses:

```python
from botocore.loaders import Loader
from botocore.model import ServiceModel

loader = Loader()
versions = loader.list_api_versions(service, "service-2")
model = ServiceModel(loader.load_service_model(service, "service-2", versions[-1]))
op = model.operation_model(pascal_name)
shape = op.input_shape
required = list(shape.required_members) if shape is not None else []
```

Two gotchas, both hit during this research:

- **`input_shape` can be `None`** for genuinely argument-less operations (e.g. `sts:GetCallerIdentity`). Guard with `if shape is not None` before touching `required_members` — `check_parameter_requirements` already does via `hasattr`.
- **Case-insensitive operation lookup is needed.** `to_pascal_case("list_saml_providers")` yields `ListSamlProviders`, but botocore's operation is `ListSAMLProviders`. `ShapeCache.get_operation_shape` already implements the case-insensitive fallback (shapes.py:70-84); the validation test must do the same (match `op.lower() == pascal.lower()` over `model.operation_names`).

Note the rule is about *shape-declared* required members. `batch:ListJobs` declares none but errors at runtime without a filter — that is why the curated pick for `batch` is `describe-compute-environments`, not `list-jobs`.

### Q3 — The curated map (50 entries, fully verified)

Every entry below was checked programmatically against botocore 1.43.89 and passed all four gates: (a) the service exists, (b) the operation exists (case-insensitively), (c) `input_shape.required_members` is empty, (d) `is_readonly_operation()` returns `True` for the kebab spelling. All 50 additionally already have curated columns in `default_filters.yaml`, so the default-column criterion is satisfied for every one. **0 failures.**

```yaml
# src/awsquery/default_actions.yaml
# Per-service default action for `awsquery <service>` with no action.
# Values are kebab-case CLI operation names, exactly as a user would type them.
# Every entry must be ReadOnly and take no required parameters — enforced by
# tests/unit/test_default_column_filters.py::TestDefaultActionsMap.
acm: list-certificates
apigateway: get-rest-apis
apigatewayv2: get-apis
appsync: list-graphql-apis
athena: list-work-groups
autoscaling: describe-auto-scaling-groups
backup: list-backup-vaults
batch: describe-compute-environments
cloudformation: describe-stacks
cloudfront: list-distributions
cloudwatch: describe-alarms
codebuild: list-projects
codecommit: list-repositories
codepipeline: list-pipelines
directconnect: describe-connections
dynamodb: list-tables
ec2: describe-instances
ecr: describe-repositories
ecs: list-clusters
efs: describe-file-systems
eks: list-clusters
elasticache: describe-cache-clusters
elasticbeanstalk: describe-environments
elb: describe-load-balancers
elbv2: describe-load-balancers
es: list-domain-names
events: list-rules
firehose: list-delivery-streams
fsx: describe-file-systems
glue: get-databases
iam: list-users
kafka: list-clusters
kinesis: list-streams
kms: list-keys
lambda: list-functions
logs: describe-log-groups
organizations: list-accounts
rds: describe-db-instances
redshift: describe-clusters
route53: list-hosted-zones
s3: list-buckets
sagemaker: list-endpoints
secretsmanager: list-secrets
ses: list-identities
sns: list-topics
sqs: list-queues
ssm: describe-parameters
stepfunctions: list-state-machines
sts: get-caller-identity
xray: get-sampling-rules
```

**Deliberately skipped (5 of the 55 services in `default_filters.yaml`)** — every one has **zero** ReadOnly operations with no required parameters, so the locked "no required parameters" rule excludes them outright:

| Service | Why skipped |
|---------|-------------|
| `application-autoscaling` | `DescribeScalableTargets` requires `ServiceNamespace`. No parameterless candidate exists. |
| `budgets` | `DescribeBudgets` requires `AccountId`. No parameterless candidate exists. |
| `ce` | Every Cost Explorer query requires `TimePeriod`; the 8 parameterless ops (`ListCostAllocationTags`, …) are all administrative and none is configured in `default_filters.yaml`. |
| `cognito-identity` | `ListIdentityPools` requires `MaxResults`. No parameterless candidate exists. |
| `cognito-idp` | `ListUserPools` requires `MaxResults`. No parameterless candidate exists. |

These five get the Q6 fallback: `awsquery budgets` lists budgets' ReadOnly actions on stderr and exits 1.

**Judgement calls to sanity-check before merge** (all pass the four mechanical gates; the ambiguity is purely "which one is *the* default"). I applied a single tie-breaker: the operation whose noun is the service's root resource — the thing everything else hangs off.

| Service | Chosen | Runner-up | Note |
|---------|--------|-----------|------|
| `iam` | `list-users` | `list-roles` | Highest-disagreement entry. Users is the console landing and the service's primary noun; roles is the more infra-centric answer. One-line change if the maintainer disagrees. |
| `ssm` | `describe-parameters` | `describe-instance-information` | Parameter Store is the dominant `awsquery ssm` use in this repo's own README examples. |
| `sagemaker` | `list-endpoints` | `list-models`, `list-training-jobs` | SageMaker has no single root resource. Included rather than skipped to keep coverage at 50; genuinely arbitrary. |
| `glue` | `get-databases` | `get-jobs` | Catalog root. |
| `backup` | `list-backup-vaults` | `list-backup-plans` | Recovery points live in vaults. |
| `athena` | `list-work-groups` | `list-query-executions` | Everything in Athena is scoped to a workgroup. |
| `batch` | `describe-compute-environments` | `list-jobs` | `ListJobs` declares no required members but errors at runtime without a queue filter — avoided on purpose. |
| `elb` / `elbv2` | both `describe-load-balancers` | — | Intentionally the same operation name on two different services; not a copy-paste error. |
| `es` | `list-domain-names` | — | `es` is legacy Elasticsearch Service, not `opensearch`. |

### Q4 — Canonical YAML value format: **kebab-case, mandatory**

This is a correctness constraint, not a style choice. `security.is_readonly_operation` (security.py:41-44) only converts to PascalCase when the input contains `-`:

```python
if "-" in action:
    action = to_pascal_case(action.replace("-", "_"))
for prefix in SAFE_READONLY_PREFIXES:
    if action.startswith(prefix): ...
```

Executed against the real function:

```
describe_instances    is_readonly=False   <-- snake_case FAILS
describe-instances    is_readonly=True
list_buckets          is_readonly=False   <-- snake_case FAILS
list-buckets          is_readonly=True
get_caller_identity   is_readonly=False   <-- snake_case FAILS
get-caller-identity   is_readonly=True
```

A snake_case default therefore reaches `prompt_unsafe_operation()` at cli.py:977, which prints "WARNING: Operation 'ec2:describe_instances' may not be read-only" and **blocks on `input()`**. `awsquery ec2` would hang in a pipe. The CONTEXT.md illustrative example `ec2: describe_instances` is snake_case; the case format was explicitly left to research discretion, and the answer is kebab.

**Where conversion happens:** at the injection boundary only, one line:

```python
action = to_kebab_case(normalize_action_name(action))
```

`normalize_action_name` is `to_snake_case`, which accepts kebab, snake, or Pascal; `to_kebab_case` then emits the canonical form. This makes the loader tolerant of any spelling while keeping the file canonical. I verified `to_snake_case` agrees with `botocore.xform_name` for every acronym operation in the map, so the round-trip is lossless.

Add a one-line assertion to the map-validation test that every YAML value already equals `to_kebab_case(to_snake_case(value))`, so the file itself stays canonical and the defensive normalisation never has to do real work.

Note the *keys* stay lowercase service names (`elbv2`, `stepfunctions`, `cognito-idp`), matching `default_filters.yaml` and botocore's own service ids. Downstream, `determine_column_filters` (cli.py:342) calls `normalize_action_name(action)` itself, so kebab actions correctly index the snake_case `default_filters.yaml` keys.

### Q5 — Test files to extend (no new files)

Everything fits into four existing files. Searched with `grep -rn "test.*parser\|test.*flag\|default_action" tests/` — no existing coverage of this feature and no candidate for a new file.

| File | Add | Assertions |
|------|-----|------------|
| `tests/unit/test_config_loading_simple.py` | New class `TestDefaultActionsConfig` next to `TestDefaultFiltersConfig` | `load_default_actions()` returns a non-empty `dict[str, str]`; `get_default_action("ec2") == "describe-instances"`; `get_default_action("EC2") == get_default_action("ec2")` (case-insensitive, mirrors `test_get_default_columns_with_real_config`); `get_default_action("budgets") is None`; `get_default_action("nonexistent") is None`; `get_default_action("") is None`; `load_default_actions.cache_info().hits` grows on a second call (mirrors `TestLoadDefaultFilters::test_caching_behavior`). |
| `tests/unit/test_default_column_filters.py` | New class `TestDefaultActionsMap` next to `TestYAMLConfigurationStructure` (which already reaches into botocore via the audit script, so this is the established home for data-validation tests) | **The whole-map guard.** `@pytest.mark.parametrize` over `sorted(load_default_actions().items())` — `parametrize` is the one marker CLAUDE.md permits — asserting per entry: (1) service is in `Loader().list_available_services("service-2")`; (2) the operation resolves case-insensitively in `model.operation_names`; (3) `input_shape is None or not input_shape.required_members`; (4) `security.is_readonly_operation(action) is True`; (5) `action == to_kebab_case(to_snake_case(action))`; (6) `to_snake_case(action) in load_default_filters()[service]` so the defaulted action always has curated columns. Plus one non-parametrized test asserting `set(load_default_actions()) <= set(load_default_filters())`. |
| `tests/unit/test_cli_parser.py` | New class `TestDefaultActionInjection` (this file already owns separator-parsing behavior) | Pure-function tests on `_inject_default_action`, **no mocks at all** — it takes a list and returns a list: `["ec2"] -> ["ec2","describe-instances"]`; `["ec2","--","InstanceId"] -> ["ec2","describe-instances","--","InstanceId"]`; `["-j","ec2","--","X"]` injects at index 2; `["--region","us-west-2","ec2"]` does not treat `us-west-2` as the service; `["ec2","describe-instances","--","X"]` is returned unchanged; `["ec2","prod"]` unchanged; `["budgets"]` unchanged; `[""]` unchanged; `[]` unchanged; `["--help"]` unchanged. Then the equivalence tests: with `boto3` mocked only, run `main()` for `["awsquery","ec2","--","InstanceId"]` and for `["awsquery","ec2","describe-instances","--","InstanceId"]` and assert `format_table_output` received identical column filters. |
| `tests/unit/test_cli_flags.py` | Extend `TestCLIFlagHandling` | Flag pass-through on a defaulted action — `["awsquery","ec2","-j"]` produces JSON output for `describe_instances`; `["awsquery","-d","ec2"]` emits the "Using default action" line on stderr; `["awsquery","ec2","-p","MaxResults=5"]` reaches `execute_aws_call` with the parameter. |
| `tests/integration/test_end_to_end.py:889` | **Rewrite** `test_main_function_service_listing` | Split into: `awsquery` (no args) still prints "Available services:" on stdout and exits 0; `awsquery budgets` writes the action list to **stderr** (check stderr, not stdout) and exits non-zero. |

Readonly-validation coverage: assert `validate_readonly` is reached with the *kebab* form for a defaulted action, and add a direct `is_readonly_operation("describe-instances") is True` / `is_readonly_operation("describe_instances") is False` pair to `tests/unit/test_security.py::TestReadOnlyOperations` so the casing trap is pinned by a test rather than a comment.

Style constraints for all of the above (CLAUDE.md): no `@pytest.mark.*` except `parametrize`; mock `boto3` only, never `filter_resources`/`determine_column_filters`/`get_default_action`; no more than two nested `with patch()`; no docstring that restates the test name.

### Q6 — The fallback path

Replace the single branch at cli.py:830-833 with two:

```python
    if not args.service:
        services = get_aws_services()
        print("Available services:", ", ".join(services))
        sys.exit(0)

    if not args.action:
        _print_service_actions(sanitize_input(args.service))
        sys.exit(1)
```

and add, next to `action_completer`:

```python
def _print_service_actions(service):
    """List a service's read-only actions on stderr when no default is configured."""
    operations = get_service_operations(service)
    if not operations:
        print(f"ERROR: Unknown service '{service}'", file=sys.stderr)
        return
    valid = get_service_valid_operations(service, operations)
    actions = sorted(to_kebab_case(op) for op in operations if op in valid)
    print(
        f"No default action configured for '{service}'. Available actions:",
        file=sys.stderr,
    )
    for action in actions:
        print(f"  {action}", file=sys.stderr)
```

**Reuse, not a new helper.** This is the same four-step sequence `action_completer` runs at cli.py:638-655 (`get_service_operations` → `get_service_valid_operations` → `to_kebab_case` → `sorted`). All three names are already imported into `cli.py` (lines 15, 33, 39) — zero new imports. Extracting a *shared* helper between `action_completer` and this function is possible but not worth it: the completer additionally mutates `_current_completion_context` and swallows every exception, so the shared core would be a 3-line list comprehension.

`get_service_operations` uses `_BotocoreSessionContext`, which pops `AWS_PROFILE` and needs no credentials, and returns `[]` for an unknown service — hence the explicit unknown-service message before the listing.

Ordering note: both branches must stay **after** the `filter_argv` / `parse_multi_level_filters_for_mode` block (cli.py:824-828) exactly as today, or `-d` debug output ordering changes. Nothing in that block depends on `args.action` being non-`None`.

### Q7 — README changes

| Location | Change |
|----------|--------|
| `README.md:295` — "### Default Filters Configuration" | Add a sibling **"### Default Actions Configuration"** subsection under `## Configuration`: explain that `awsquery <service>` with no action runs the service's curated default, that the map lives in `src/awsquery/default_actions.yaml` as a flat `service: action` map in kebab-case, and that adding a service is a one-line YAML edit. Show the shortcut table: `awsquery ec2` ≡ `awsquery ec2 describe-instances`, `awsquery s3` ≡ `awsquery s3 list-buckets`. State the two rules an entry must satisfy (ReadOnly, no required parameters) and that a service without an entry prints its available actions on stderr and exits non-zero. |
| `README.md:455-462` — "#### Additive Column Filters (`+Column`)" table | Add a row so the shortcut is visible where columns are explained: `awsquery ec2 -- +InstanceId` → "defaults + `InstanceId`, using the `ec2` default action". |
| `README.md` Quick Start / usage examples (near line 30, "Default Column Filters" bullet) | Add a **"Default Actions"** bullet to the feature list and one bare-service example (`awsquery ec2`, `awsquery s3 -- Name`) so the shortcut is discoverable above the fold. |
| `cli.py:672-700` parser `epilog` | Add two example lines to the existing `Examples:` block — `awsquery ec2  (uses the default action, describe-instances)` and `awsquery s3 -- Name  (default action + column filter)`. Note `tests/unit/test_cli_help_output.py` asserts on epilog content; check it still passes. |

## Architecture Patterns

### Recommended Approach

1. **Data before code.** Add `src/awsquery/default_actions.yaml` and register it in `pyproject.toml:82` (`awsquery = ["policy.json", "default_filters.yaml", "default_actions.yaml"]`) in the same commit. Omitting the package-data entry produces a wheel that silently has no defaults — `load_default_actions()` returns `{}` and every service falls back. There is no `MANIFEST.in`; `pyproject.toml:82` is the only packaging list in the repo.
2. **Loader by copy-paste-and-adapt.** `load_default_actions()` is `load_default_filters()` with a different filename; `get_default_action()` is the two-line analogue of `get_default_columns()`. Keep the `# pragma: no mutate` markers on the `debug_print` calls — the repo runs mutmut (`[tool.mutmut]` in pyproject) and every debug string in `config.py` carries one.
3. **One pure function for the CLI change.** `_inject_default_action(argv) -> argv` takes a list and returns a list. It is trivially testable with no mocks, which is precisely what CLAUDE.md's "test real implementation, mock boto3 only" rule wants.
4. **Split the dead-end branch, don't extend it.** Two `if`s replacing one, plus a 10-line stderr helper.
5. **Guard the data with one parametrized test**, not with prose.

### Anti-Patterns to Avoid

- **Substituting on `args.action is None` after parsing.** Proven insufficient — see Q1. This is the approach the ISSUE.md text implies, and it fails the `--` acceptance criterion silently.
- **Storing snake_case in the YAML.** Proven to break `validate_readonly` into an interactive prompt — see Q4.
- **Mutating `sys.argv` in place.** Line 762 and line 806 read it; tests assign it. Pass the normalized list to `parse_known_args()` instead.
- **Demoting an unrecognised second positional to a value filter.** Turns typos into silent zero-row results and adds a botocore load to the hot path — see Q1.
- **Adding a `default_action:` key inside `default_filters.yaml`.** Locked against, and confirmed to break `test_columns_are_strings`, `test_descriptions_not_required`, and `audit_default_filters.py:71` with `AttributeError: 'str' object has no attribute 'get'`.
- **Printing the default-action hint on stderr during normal runs.** Locked to `debug_print` only — stderr already carries the "Using default columns:" line, and a second unconditional line degrades piping.
- **Creating `tests/unit/test_default_actions.py`.** CLAUDE.md forbids duplicate test files; all five extension points are existing files.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cached YAML config load with error fallbacks | A new loader idiom | Copy `load_default_filters()`'s `@lru_cache(maxsize=1)` + three-`except` structure | Identical requirements; the locked decision mandates mirroring it |
| kebab ↔ snake ↔ Pascal conversion | Regex or an acronym dictionary | `case_utils.to_kebab_case` / `to_snake_case` / `to_pascal_case` | Verified to agree with `botocore.xform_name` for every acronym in the map |
| "Is this operation read-only?" | A new prefix list or a policy.json parse | `security.is_readonly_operation()` | `policy.json` is **no longer consulted by any code path** — `security.py` is pure prefix matching. The file ships but is dead weight for this feature. |
| Listing a service's ReadOnly actions | New botocore traversal | `get_service_operations()` + `get_service_valid_operations()` + `to_kebab_case` | Already imported in `cli.py`; the exact sequence `action_completer` uses |
| Credential-free service model access in tests | `boto3.client()` | `botocore.loaders.Loader` (as `shapes.ShapeCache` does) | `boto3.client()` needs a region and sometimes credentials; the Loader needs neither |
| Required-parameter introspection at runtime | New model walk | `core.check_parameter_requirements()` | Already handles `input_shape is None` and returns a safe default on any exception |
| Flag/value tokenisation in the injector | A new parser | The existing `SIMPLE_FLAGS` / `VALUE_FLAGS` constants (cli.py:237-238) | Single source of truth; `_extract_flag_and_value` uses the same rule |

## Common Pitfalls

### snake_case default silently becomes an interactive prompt
**What goes wrong:** `awsquery ec2` prints "WARNING: Operation 'ec2:describe_instances' may not be read-only" and blocks on `input()`.
**Why:** `is_readonly_operation` only PascalCases when `"-" in action` (security.py:42).
**How to avoid:** kebab-case in the YAML + `to_kebab_case(normalize_action_name(v))` at injection.
**Warning signs:** the tool hangs when piped; `Do you want to proceed? (yes/no):` on a read-only command.

### `awsquery ec2 -- InstanceId` runs an operation called `InstanceId`
**What goes wrong:** the first column filter is consumed as the action; a column is also dropped.
**Why:** argparse strips the leading `--` and fills the `nargs="?"` `action` positional.
**How to avoid:** pre-parse injection (Q1).
**Warning signs:** `ERROR: Operation ec2:InstanceId was not allowed`, or an unsafe-operation prompt for a column name.

### Wheel ships without the map
**What goes wrong:** `pip install awsquery` → every service falls back to the action listing; works perfectly from a source checkout.
**Why:** `[tool.setuptools.package-data]` at `pyproject.toml:82` is the only packaging list; there is no `MANIFEST.in`.
**How to avoid:** add `default_actions.yaml` in the same commit.
**Warning signs:** cannot be caught by the unit tests, which read from the source tree. Verify with `python -m build && unzip -l dist/*.whl | grep yaml`.

### The vacuously-green integration test
**What goes wrong:** `test_end_to_end.py:889` guards its assertions with `if "Available services:" in output`. After the change that string is gone, the test passes while `main()` actually attempts a real AWS call under a partially-mocked `boto3.Session`.
**How to avoid:** rewrite it (Q5) rather than letting it "still pass".
**Warning signs:** the test suite slows down, or fails only on machines without AWS config.

### `input_shape is None` for truly parameterless operations
**What goes wrong:** `AttributeError: 'NoneType' object has no attribute 'required_members'` in the validation test, on `sts:GetCallerIdentity` among others.
**How to avoid:** `required = list(shape.required_members) if shape is not None else []`.

### Acronym operations don't resolve by PascalCase alone
**What goes wrong:** `to_pascal_case("list_saml_providers")` → `ListSamlProviders`, which is not in `operation_names` (the real name is `ListSAMLProviders`).
**How to avoid:** case-insensitive match over `model.operation_names`, as `shapes.py:70-84` already does. Affects `iam:list-users`' neighbours and `elbv2:describe-ssl-policies` if the map is ever extended.

### Shape-declared-required is not the same as runtime-required
**What goes wrong:** `batch:ListJobs` declares no required members but errors without a queue filter; `logs:DescribeLogStreams` correctly declares `LogGroupName` and is excluded automatically.
**How to avoid:** the mechanical gate is necessary but not sufficient — the curated picks in Q3 were chosen with this in mind (`batch` → `describe-compute-environments`).

## Environment Availability

| Dependency | Required By | Available | Version | Note |
|------------|------------|-----------|---------|------|
| Python | everything | Yes | 3.13 (`/usr/bin/python3.13`) | |
| `botocore` | runtime + validation test | **No** (system python) | 1.43.89 when installed | Not importable in this container's default interpreter; `make test` presumably runs in the project's Docker image. Installed to a scratchpad prefix for this research. |
| `boto3` | runtime | **No** (system python) | — | Same |
| `argcomplete` | `cli.py` import | **No** (system python) | — | Blocks `import awsquery` in a bare shell — I loaded `case_utils.py` via `importlib` to test it in isolation |
| `PyYAML` | config loading | No (system python) | 6.0.3 when installed | |
| `pytest` | tests | Not verified | — | `make test` / Docker path |
| Docker | `make test-in-docker` | Not probed | — | |
| AWS credentials | live calls only | Not required | — | `_BotocoreSessionContext` and `botocore.loaders.Loader` both work credential-free |

Implication for planning: the map-validation test needs only `botocore` (already a hard dependency in `pyproject.toml`) and no AWS credentials, so it runs in CI unchanged. Any verification command the plan proposes must run inside the project environment (`make test`), not the bare shell.

## Project Constraints (from CLAUDE.md)

- **ZERO backward compatibility.** Change `main()`'s internal structure freely; only the CLI UX must stay stable. Splitting cli.py:830 into two branches is exactly the sanctioned kind of change.
- **NO pytest markers.** `@pytest.mark.parametrize` is the only permitted decorator. The map-validation test uses it; nothing else may carry a marker. (Note: CLAUDE.md's own "Testing Structure" and "Single Test Execution" sections still mention `@pytest.mark.unit` and `-m "unit"` — those are stale relative to the absolute prohibition later in the same file. Follow the prohibition.)
- **No over-mocking.** Mock `boto3` only. `_inject_default_action` and `get_default_action` must be exercised for real; never patch `get_default_action` in a CLI test.
- **Max 2 nested `with patch()`.** Existing `test_cli_parser.py` tests already sit at 3 nested contexts — do not use them as the template for new tests; prefer decorator-stacked `@patch` as `test_cli_flags.py` does.
- **No duplicate test files.** All five extension points are existing files; do not create `test_default_actions.py`.
- **No verbose/redundant test docstrings.** No docstring that restates the test name; no TDD placeholders.
- **Mandatory specialised agents.** Python implementation → `@agent-python-infra-automator`; tests → `@agent-test-writer`; review after changes → `@agent-code-reviewer`. Any `Makefile` touch → `@agent-makefile-optimizer` (none expected here).
- **Commits: single line, ≤72 chars**, no bullets, no multi-line body. Suggested split: `Add curated default_actions.yaml and config loader` / `Default the action when only a service is given` / `Document default action shortcut`.
- **No AI attribution** in code comments or files (global policy). Note this conflicts with CLAUDE.md's "COMMIT FORMAT" trailer block — the global no-attribution rule wins; ask before adding any trailer.
- **Line length 100** (black, flake8, pylint all configured to 100).
- **flake8-docstrings is enabled** with `D103` ignored but `D100/D101/D102` active outside `tests/*` — new functions in `cli.py`/`config.py` need docstrings.
- **Quality gates:** `make test`, `make lint`, `make format-check` must pass; `make format` runs black + isort (profile=black, line_length=100).

## Sources

### HIGH confidence
- Direct reads of `src/awsquery/{cli,config,security,utils,case_utils,filters,core,shapes}.py`, `tests/unit/test_default_column_filters.py`, `tests/unit/test_config_loading_simple.py`, `tests/unit/test_cli_parser.py`, `tests/integration/test_end_to_end.py`, `scripts/audit_default_filters.py`, `pyproject.toml`, `pytest.ini`, `.flake8`, `README.md` — all in the ty5dx worktree checkout.
- **Executed** the project's argparse configuration over 9 command shapes → the `--`-eats-the-action finding.
- **Executed** a faithful replay of `main()`'s reorder pass plus the real `parse_multi_level_filters_for_mode` source over 11 bare/explicit command pairs → "ALL EQUIVALENT: True".
- **Executed** `case_utils.to_snake_case` against `botocore.xform_name` for 12 acronym operations → exact match on all.
- **Executed** the project's own `SAFE_READONLY_PREFIXES` logic over snake vs kebab spellings → the `validate_readonly` casing trap.
- **Executed** a four-gate validation of all 50 curated entries against botocore 1.43.89 service models → 0 failures, all 50 also present in `default_filters.yaml`.
- **Executed** a sweep of all 55 `default_filters.yaml` services for ReadOnly + zero-required-member operations → the 5-service skip list.

### MEDIUM confidence
- The "which operation is *the* default" tie-breaks for `iam`, `ssm`, `sagemaker`, `glue`, `backup`, `athena` — mechanically valid, editorially arguable. Flagged individually in Q3.
- `batch:ListJobs` erroring at runtime without a queue filter — from AWS API behavior knowledge, not verified against a live account. It is avoided regardless.

### LOW confidence (needs validation)
- Whether `make test` currently passes on a clean checkout — not run (no `pytest`/`boto3` in this container's interpreter). The plan should treat the existing suite as green-until-proven-otherwise and re-verify inside the project environment.

## Metadata

**Confidence breakdown**

| Area | Level | Reason |
|------|-------|--------|
| Insertion point (Q1) | HIGH | Empirically proven by executing the real parser and a pipeline replay; equivalence demonstrated over 11 command pairs |
| Required-parameter detection (Q2) | HIGH | Read from `core.py`/`shapes.py` and executed against botocore |
| Curated map (Q3) | HIGH (mechanical) / MEDIUM (editorial) | All 50 pass four automated gates; 6 entries are judgement calls, flagged |
| YAML casing (Q4) | HIGH | Executed the real `is_readonly_operation` logic both ways |
| Test targets (Q5) | HIGH | Every named file read; no duplicate-file risk; one existing test identified as needing rewrite |
| Fallback path (Q6) | HIGH | Helpers confirmed already imported in `cli.py`; sequence copied from `action_completer` |
| README changes (Q7) | HIGH | Exact line numbers read and confirmed |
| Environment | MEDIUM | System interpreter lacks the project's deps; conclusions drawn from a scratchpad install of botocore 1.43.89 |

**Research date:** 2026-09-08
**Method:** single-agent, verification-first — no sub-agent delegation was used (the `Agent` tool was unavailable in this session). Every load-bearing claim was verified by executing code rather than by inference; unverified claims are marked MEDIUM/LOW above.
**Raw research files:** none — findings verified inline and consolidated directly into this document.
