# Plan: Add per-service default actions so `awsquery ec2` runs without an action

<objective>
What this plan accomplishes: `awsquery <service>` with no action resolves a curated
per-service default operation (`awsquery ec2` == `awsquery ec2 describe-instances`,
`awsquery s3` == `awsquery s3 list-buckets`), while `awsquery <service> -- <filters>`
behaves identically to the explicit form. Services without a curated default print that
service's ReadOnly actions on stderr and exit non-zero. `awsquery` with no service at all
is unchanged (services on stdout, exit 0).

Why it matters: today `awsquery ec2` falls into the `if not args.service or not args.action`
dead end at `cli.py:830` and dumps the full AWS service list — ignoring the service the user
just typed. `awsinfo` treats a bare service name as its most common read operation; this
brings the same affordance.

Scope IN: new `src/awsquery/default_actions.yaml` (50 curated entries) + packaging entry;
`load_default_actions()` / `get_default_action()` in `config.py`; pre-parse argv injection in
`cli.py`; the no-default stderr fallback; tests in five EXISTING test files; README + parser
epilog docs.

Scope OUT (deferred in CONTEXT.md, do not implement): botocore heuristic inference for
uncurated services; default *parameters* attached to a default action; user-level override
(`~/.awsquery/`); refreshing `.issues/MAP.md`.
</objective>

<strategy>
**Direction.** Resolve the default *before* argparse sees the tokens, not after.

**Why.** ISSUE.md frames this as "when `args.action` is empty, substitute the default." The
research disproved that framing by executing the real parser: `service` and `action` are both
`nargs="?"`, so argparse eats the `--` separator and promotes the first column filter into the
`action` slot. `['ec2','--','InstanceId']` parses to `service='ec2', action='InstanceId',
remaining=[]` — byte-identical to `['ec2','InstanceId']`. Post-parse the two are
indistinguishable, so a post-parse patch leaves `awsquery ec2 -- InstanceId` running a bogus
operation named `InstanceId` and silently fails an acceptance criterion. The information only
exists in the raw token list.

**Options considered.**
1. *Post-parse substitution on `args.action is None`* (what ISSUE.md implies) — REJECTED,
   provably insufficient per above.
2. *Pre-parse argv injection* — CHOSEN. One pure `list -> list` function called on
   `sys.argv[1:]` at `cli.py:752`. Everything downstream (`_build_filter_argv`, the two-pass
   reorder, `parse_multi_level_filters_for_mode`, `validate_readonly`,
   `check_parameter_requirements`, `determine_column_filters`) then sees exactly the argv the
   user "would have typed", so every acceptance criterion holds *by construction* rather than
   via a parallel code path. Research replayed the real pipeline over 11 bare/explicit command
   pairs: all equivalent.
3. *Look the second positional up in `get_service_operations()` and demote non-operations to
   value filters* (so `awsquery ec2 prod` would also default) — REJECTED: a typo like
   `awsquery ec2 describe-instance` would then silently run `describe-instances` with a
   spurious value filter and print zero rows instead of erroring, and it costs a botocore
   model load on the hot path. Structural detection (next token absent / `--` / starts with
   `-`) satisfies every criterion without that trap.

**Second load-bearing decision: kebab-case in the YAML is mandatory, not stylistic.**
`security.is_readonly_operation` only PascalCases its input when the string contains `-`.
Given `describe_instances` it returns `False`, falls through to `prompt_unsafe_operation()`
and **blocks on `input()`** — `awsquery ec2` would hang in a pipe. CONTEXT.md's illustrative
`ec2: describe_instances` is snake_case and is therefore overridden (casing was explicitly
left to research discretion). The file holds kebab-case; the injector additionally applies
`to_kebab_case(to_snake_case(v))` defensively.

**Third: a separate file, not a key in `default_filters.yaml`.** Locked in CONTEXT.md, and
confirmed empirically: `scripts/audit_default_filters.py:71` and
`tests/unit/test_default_column_filters.py:350,362` both walk `service -> action -> {...}`
and would raise `AttributeError: 'str' object has no attribute 'get'` on a sibling string key.

**Key decision points for the reviewer:** the six editorially arguable curated picks below
(`iam` is the flagged one) — each is a one-line YAML change.
</strategy>

## Maintainer review — editorially arguable curated picks (SURFACED FOR VETO)

All 50 entries pass four mechanical gates (real botocore operation, zero required shape
members, ReadOnly by the project's prefix rule, already has curated columns in
`default_filters.yaml`). These six are nonetheless **judgement calls** about which operation is
*the* default. The tie-breaker applied was "the operation whose noun is the service's root
resource". **Each is a one-line change in `src/awsquery/default_actions.yaml`; flag any
disagreement at review and the executor edits that single line.**

| Service | Chosen | Runner-up | Why chosen / how contestable |
|---------|--------|-----------|------------------------------|
| **`iam`** | `list-users` | `list-roles` | **Highest-disagreement entry.** Users is the console landing page and IAM's primary noun; `list-roles` is the more infra-centric answer and a defensible override. |
| `ssm` | `describe-parameters` | `describe-instance-information` | Parameter Store dominates `ssm` usage in this repo's own README examples. |
| `sagemaker` | `list-endpoints` | `list-models`, `list-training-jobs` | SageMaker has no single root resource — genuinely arbitrary. Included rather than skipped to keep coverage at 50. |
| `glue` | `get-databases` | `get-jobs` | Catalog is the root. |
| `backup` | `list-backup-vaults` | `list-backup-plans` | Recovery points live in vaults. |
| `athena` | `list-work-groups` | `list-query-executions` | Everything in Athena is scoped to a workgroup. |

Two non-obvious-but-deliberate entries (not up for debate, documented so they are not
"fixed" as bugs): `elb` and `elbv2` intentionally share the operation name
`describe-load-balancers` (two different services); `batch` uses
`describe-compute-environments` rather than `list-jobs` because `ListJobs` declares no
required members but errors at runtime without a queue filter.

<skills>
This repo has no `.claude/skills/` directory. Container-level skills that apply:
- @/root/.claude/skills/python/SKILL.md — all `.py` edits in this plan

Repo CLAUDE.md additionally mandates specialised agents (binding on the executor):
`@agent-python-infra-automator` for Python implementation, `@agent-test-writer` for all test
work, `@agent-code-reviewer` proactively after the code changes land.
</skills>

<context>
Issue: @.issues/ty5dx-add-per-service-default-actions-so-awsquery-ec2-runs-without-an-action/ISSUE.md
Research: @.issues/ty5dx-add-per-service-default-actions-so-awsquery-ec2-runs-without-an-action/RESEARCH.md
Decisions: @.issues/ty5dx-add-per-service-default-actions-so-awsquery-ec2-runs-without-an-action/CONTEXT.md

**Precedence when sources conflict: RESEARCH.md > CONTEXT.md > ISSUE.md.** Research verified
its claims by executing code and overturned exactly two points: (a) ISSUE.md's "substitute
when `args.action` is empty" is wrong — use pre-parse argv injection; (b) CONTEXT.md's
illustrative snake_case YAML (`ec2: describe_instances`) is wrong — values MUST be kebab-case.
Every other locked decision in CONTEXT.md stands unchanged.

<interfaces>
<!-- Executor: use these contracts directly. Do not explore the codebase for them. -->

# ── src/awsquery/config.py (EXISTING — the exact shape to mirror) ────────────
@lru_cache(maxsize=1)
def load_default_filters():                       # -> dict | {} on any error
    config_path = os.path.join(os.path.dirname(__file__), "default_filters.yaml")
    # try: open + yaml.safe_load + debug_print(...)  # pragma: no mutate
    # except FileNotFoundError / yaml.YAMLError / Exception: debug_print(...); return {}
def get_default_columns(service, action):         # -> list[str] ([] when unset)
    # config.get(service.lower(), {}).get(action.lower(), {}).get("columns", [])
    # debug_print on BOTH hit and miss, each with a trailing  # pragma: no mutate
def apply_default_filters(service, action, user_columns=None, additive=False)

# NEW in config.py — mirror the above exactly (including # pragma: no mutate markers):
@lru_cache(maxsize=1)
def load_default_actions():                       # -> dict[str, str] | {}
def get_default_action(service):                  # -> str | None

# ── src/awsquery/cli.py (EXISTING) ──────────────────────────────────────────
# line 237-238:
SIMPLE_FLAGS = ["-d", "--debug", "-j", "--json", "-k", "--keys", "--allow-unsafe"]
VALUE_FLAGS  = ["--region", "--profile", "-p", "--parameter", "-i", "--input"]
def _build_filter_argv(args, remaining)           # line 298 — needs NO change
def action_completer(prefix, parsed_args, **kwargs)  # line 632 — needs NO change
def main()                                        # line 668
#   line 674-699: parser epilog with the `Examples:` block
#   line 749: argcomplete.autocomplete(parser, validator=_enhanced_completion_validator)
#   line 752: args, remaining = parser.parse_known_args()          <-- INJECTION CALL SITE
#   line 762: has_separator = "--" in sys.argv                     <-- reads sys.argv directly
#   line 806: reordered_argv = [sys.argv[0]]                       <-- reads sys.argv directly
#   line 830: if not args.service or not args.action:              <-- SPLIT INTO TWO BRANCHES
#                 services = get_aws_services(); print("Available services:", ...); sys.exit(0)

# NEW in cli.py:
def _inject_default_action(argv)                  # -> list[str] (pure; must never raise)
def _print_service_actions(service)               # -> None (writes stderr)

# cli.py CURRENT imports (verified) — these are ALREADY available, add no duplicates:
from .case_utils import to_kebab_case                             # line 15
from .config import apply_default_filters                         # line 16  <-- ADD get_default_action
from .security import get_service_valid_operations, validate_readonly   # lines 32-35
from .utils import (_BotocoreSessionContext, create_session, debug_print,
                    get_aws_services, get_service_operations, sanitize_input)  # lines 36-43
# NOT currently imported and REQUIRED by the injector:
from .case_utils import to_kebab_case, to_snake_case              # extend line 15

# ── src/awsquery/security.py ────────────────────────────────────────────────
SAFE_READONLY_PREFIXES = ["List","Get","Describe","BatchGet","BatchDescribe","BatchCheck",
    "BatchDetect","Search","Query","View","Lookup","Read","Scan","Select","Check","Validate",
    "Test","Preview","Verify","Estimate","Discover","Retrieve","Has"]
def is_readonly_operation(action: str) -> bool
    # security.py:41-44:  if "-" in action: action = to_pascal_case(action.replace("-","_"))
    # ⚠ snake_case input is NEVER PascalCased -> ALWAYS returns False -> blocking input()
def validate_readonly(service, action, allow_unsafe=False) -> bool
def get_service_valid_operations(service: str, all_operations: list) -> set

# ── src/awsquery/utils.py ───────────────────────────────────────────────────
def get_service_operations(service) -> list[str]  # PascalCase op names; [] for unknown service
                                                  # uses _BotocoreSessionContext — no creds needed
def get_aws_services() -> list[str]
def sanitize_input(value) -> str
normalize_action_name = to_snake_case             # accepts kebab | snake | Pascal
def debug_print(*args, **kwargs)                  # stderr, only when debug enabled

# ── src/awsquery/case_utils.py ──────────────────────────────────────────────
def to_snake_case(text) -> str    # verified == botocore.xform_name for all 50 curated picks
def to_kebab_case(text) -> str
def to_pascal_case(text) -> str

# ── src/awsquery/shapes.py (pattern for the credential-free validation test) ─
class ShapeCache:
    def get_service_model(self, service) -> ServiceModel | None   # botocore Loader, no creds
    def get_operation_shape(self, service, operation)             # case-insensitive fallback,
                                                                  # shapes.py:70-84
# ── botocore, credential-free (use THIS in the map-validation test, not boto3.client) ──
from botocore.loaders import Loader
from botocore.model import ServiceModel
loader = Loader()
loader.list_available_services("service-2")       # -> list[str] service ids
versions = loader.list_api_versions(service, "service-2")
model = ServiceModel(loader.load_service_model(service, "service-2", versions[-1]))
model.operation_names                              # PascalCase, e.g. "ListSAMLProviders"
op = model.operation_model(pascal_name); shape = op.input_shape   # ⚠ shape MAY BE None
required = list(shape.required_members) if shape is not None else []

# ── pyproject.toml:82 (EXISTING) ────────────────────────────────────────────
[tool.setuptools.package-data]
awsquery = ["policy.json", "default_filters.yaml"]     # <-- must gain "default_actions.yaml"
# There is no MANIFEST.in. This line is the ONLY packaging list in the repo.
</interfaces>

<call_sites>
Searched: bare-service invocations of the `awsquery` CLI (`awsquery <service>` with no action),
plus every reference to the `Available services:` string this change stops emitting for the
service-given case.
Surfaces grepped: `.github/workflows/`, `Makefile`, `scripts/`, `README.md`, `tests/`.

Found:
- `README.md:83` — `awsquery ec2 <TAB>   # Shows available ec2 actions` — OUT OF SCOPE.
  Shell completion runs inside `argcomplete.autocomplete()` at cli.py:749, which `exit()`s
  before line 752; injection happens after it, so completion behaviour is untouched.
- `tests/integration/test_end_to_end.py:889` `test_main_function_service_listing` —
  `sys.argv = ["awsquery","ec2"]`, assertions guarded by `if "Available services:" in output`
  — IN SCOPE (Task 5), must be rewritten, see that task for why "still passes" is a trap.
- `tests/integration/test_end_to_end.py:629` `test_missing_service_action_edge_cases` —
  `["awsquery","","describe-instances"]` (empty service) — OUT OF SCOPE, verified safe: the
  injector sees `""` as the service candidate, `get_default_action("")` returns `None`, no
  injection occurs, and `not args.service` still fires.
- `Makefile` / `.github/workflows/*.yml` / `scripts/validate-awsquery.sh` — no bare-service
  invocation anywhere; every call passes an explicit action. OUT OF SCOPE.
- `README.md:455-462` additive-columns table and `README.md:293` Default Filters section —
  IN SCOPE (Task 6, documentation).

No other call sites found.
</call_sites>

Key files:
@src/awsquery/cli.py — injection call site (752), branch split (830), epilog (674-699)
@src/awsquery/config.py — 86 lines; the loader/accessor pair to mirror
@src/awsquery/security.py — the kebab/snake casing trap at lines 41-44
@pyproject.toml — package-data list at line 82
@tests/integration/test_end_to_end.py — the vacuously-green test at line 889
@README.md — sections at lines ~30 (feature bullets), 293, 453-462
</context>

<commit_format>
Format: plain, single-line summary, no issue prefix (per `.issues/config.yaml`
`commits: {format: plain, prefix: false}` and CLAUDE.md's commit guidelines).
Hard rules: maximum 72 characters, ONE line, no bullets, no multi-line body.
**No AI-attribution trailer** — the global no-attribution policy overrides the trailer block
shown in CLAUDE.md's "COMMIT FORMAT" example. Do not add `Co-Authored-By: Claude` or the
"Generated with Claude Code" line.
Examples: `Add curated default_actions.yaml and config loader`
          `Default the action when only a service is given`
          `Document default action shortcut`
</commit_format>

<tasks>

<task type="auto">
  <name>Task 1: Add the curated default_actions.yaml and register it for packaging</name>
  <files>src/awsquery/default_actions.yaml, pyproject.toml</files>
  <action>
  Create `src/awsquery/default_actions.yaml` as a FLAT `service: action` map. Copy the 50
  entries below VERBATIM — do not re-derive, re-order, or "improve" them. Every entry was
  verified against botocore 1.43.89 to be a real operation with zero required shape members,
  ReadOnly under the project's prefix rule, and already present in `default_filters.yaml`
  (0 failures across all 50). Values are kebab-case: this is a correctness requirement, not
  style — `security.is_readonly_operation` only PascalCases input containing `-`, so a
  snake_case value returns `is_readonly=False`, falls through to `prompt_unsafe_operation()`
  and blocks on `input()`, hanging `awsquery ec2` in a pipe.

  File contents (header comment + the map, exactly):

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

  Do NOT add entries for `application-autoscaling`, `budgets`, `ce`, `cognito-identity`,
  `cognito-idp` — each was swept and has ZERO ReadOnly operations with no required
  parameters, so the locked "no required parameters" rule excludes them. They intentionally
  get the Task 3 stderr fallback.

  Then edit `pyproject.toml:82` from
  `awsquery = ["policy.json", "default_filters.yaml"]` to
  `awsquery = ["policy.json", "default_filters.yaml", "default_actions.yaml"]`.
  This must land in the SAME commit as the YAML: there is no `MANIFEST.in`, so omitting it
  produces a wheel with no defaults that works perfectly from a source checkout and silently
  falls back for every service after `pip install`. The unit tests read from the source tree
  and CANNOT catch this.
  </action>
  <verify>
  <automated>python3 -c "
import yaml, pathlib
m = yaml.safe_load(pathlib.Path('src/awsquery/default_actions.yaml').read_text())
assert isinstance(m, dict) and len(m) == 50, len(m)
assert all(isinstance(k, str) and isinstance(v, str) for k, v in m.items())
assert all('_' not in v and v == v.lower() and '-' in v for v in m.values()), 'values must be kebab-case'
assert m['ec2'] == 'describe-instances' and m['s3'] == 'list-buckets'
assert not ({'budgets','ce','cognito-idp','cognito-identity','application-autoscaling'} & set(m))
print('map ok', len(m))" && grep -q 'default_actions.yaml' pyproject.toml && echo packaging-ok</automated>
  </verify>
  <done>
  - `src/awsquery/default_actions.yaml` exists, parses via `yaml.safe_load`, and is a flat
    `dict[str, str]` with exactly 50 entries
  - Every value is kebab-case; no value contains `_`
  - `ec2 -> describe-instances`, `s3 -> list-buckets`; none of the five skipped services present
  - `pyproject.toml:82` lists `default_actions.yaml` alongside `policy.json` and
    `default_filters.yaml`
  </done>
</task>

<task type="auto">
  <name>Task 2: Add load_default_actions() and get_default_action() to config.py</name>
  <files>src/awsquery/config.py, tests/unit/test_config_loading_simple.py</files>
  <action>
  In `src/awsquery/config.py`, add two functions modelled line-for-line on the existing
  `load_default_filters()` / `get_default_columns()` pair (locked decision in CONTEXT.md):

  - `load_default_actions()` decorated `@lru_cache(maxsize=1)`. Resolve the path as
    `os.path.join(os.path.dirname(__file__), "default_actions.yaml")`. Same three excepts
    (`FileNotFoundError`, `yaml.YAMLError`, bare `Exception`), each `debug_print`ing a warning
    and returning `{}`. Also return `{}` when `yaml.safe_load` yields a falsy value, so an
    empty file cannot make `get_default_action` raise.
  - `get_default_action(service)` returning `str | None`: `config.get(service.lower())`,
    `debug_print` on BOTH the hit and the miss path (mirroring `get_default_columns`), return
    `None` when unset. Guard against a falsy/None `service` argument so `get_default_action("")`
    returns `None` rather than raising.

  Every `debug_print` in this module carries a trailing `# pragma: no mutate` — the repo runs
  mutmut. Keep that convention on the new calls. flake8-docstrings is active outside `tests/*`
  with only `D103` ignored, so both functions need a docstring. Line length is 100.

  Do NOT touch `default_filters.yaml`, `load_default_filters`, `get_default_columns`, or
  `apply_default_filters` — the separate-file decision exists precisely so those stay untouched.

  Tests (via `@agent-test-writer`): add a new class `TestDefaultActionsConfig` to the EXISTING
  `tests/unit/test_config_loading_simple.py`, next to `TestDefaultFiltersConfig`. Do not create
  a new test file. Exercise the real loader against the real YAML — no mocking of any kind is
  needed or permitted here. Assertions: `load_default_actions()` returns a non-empty
  `dict[str, str]`; `get_default_action("ec2") == "describe-instances"`;
  `get_default_action("EC2") == get_default_action("ec2")`;
  `get_default_action("s3") == "list-buckets"`; `get_default_action("budgets") is None`;
  `get_default_action("nonexistent-service") is None`; `get_default_action("") is None`; and a
  caching test asserting `load_default_actions.cache_info().hits` grows on a second call
  (mirror `TestLoadDefaultFilters::test_caching_behavior` in
  `tests/unit/test_default_column_filters.py`). No `@pytest.mark.*` decorators. No docstring
  that merely restates the test name.
  </action>
  <verify>
  <automated>python3 -m pytest tests/unit/test_config_loading_simple.py -v && python3 -m pytest tests/unit/test_default_column_filters.py -q</automated>
  </verify>
  <done>
  - `config.load_default_actions()` is `@lru_cache(maxsize=1)` and returns `{}` on
    FileNotFoundError / YAMLError / any exception / empty file
  - `config.get_default_action(service)` is case-insensitive, `debug_print`s on hit and miss,
    returns `None` for unconfigured, unknown, and empty service names
  - New `# pragma: no mutate` markers present on every new `debug_print`
  - `TestDefaultActionsConfig` added to the existing file and passing; no new test file created
  - `load_default_filters` / `get_default_columns` / `apply_default_filters` unchanged
  </done>
</task>

<task type="auto">
  <name>Task 3: Pre-parse argv injection in cli.py plus the no-default stderr fallback</name>
  <files>src/awsquery/cli.py</files>
  <action>
  Two changes in `src/awsquery/cli.py`, both required for the acceptance criteria.

  **(a) `_inject_default_action(argv)` — a pure function, list in / list out, never raises.**
  Place it near the other argv helpers (after `_build_filter_argv`, ~line 320). Extend the
  existing imports: `from .case_utils import to_kebab_case, to_snake_case` and
  `from .config import apply_default_filters, get_default_action`. `to_kebab_case`,
  `get_service_operations`, `get_service_valid_operations`, `get_aws_services`, `sanitize_input`
  and `debug_print` are ALREADY imported — do not duplicate them.

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
              return argv
          action = get_default_action(service)
          if not action:
              return argv
          action = to_kebab_case(to_snake_case(action))
          debug_print(f"Using default action for {service}: {action}")
          return argv[: i + 1] + [action] + argv[i + 1 :]

  Scanning `VALUE_FLAGS` is required, not optional: `awsquery --region us-west-2 ec2` must not
  treat `us-west-2` as the service. The `--region=us-west-2` equals-form is not in
  `VALUE_FLAGS`, starts with `-`, and is correctly skipped as one self-contained token. The
  `to_kebab_case(to_snake_case(...))` line is the defensive canonicalisation for the casing
  trap — keep it even though Task 1's YAML is already canonical.

  **Call site — replace `cli.py:752`** `args, remaining = parser.parse_known_args()` with:

      args, remaining = parser.parse_known_args(_inject_default_action(sys.argv[1:]))

  Ordering is load-bearing: it must come AFTER `argcomplete.autocomplete(...)` (line 749),
  which reads `COMP_LINE` and `exit()`s during shell completion. **Never mutate `sys.argv`** —
  line 762 (`has_separator = "--" in sys.argv`) and line 806 (`reordered_argv = [sys.argv[0]]`)
  both read it directly, and every existing test assigns it to describe the user's real command.
  Injection never adds or removes a `--`, so line 762 stays correct.

  `_build_filter_argv` (line 298) and the two-pass reorder (755-815) need NO change — the
  reorder rebuilds `reordered_argv` from `args.service`/`args.action`, so the injected action
  survives the re-parse. `parse_multi_level_filters_for_mode` needs no change either.

  **(b) Split the dead-end branch at `cli.py:830` into two.** It must stay AFTER the
  `filter_argv` / `parse_multi_level_filters_for_mode` block (824-828) exactly as today, or
  `-d` debug output ordering changes.

      if not args.service:
          services = get_aws_services()
          print("Available services:", ", ".join(services))
          sys.exit(0)

      if not args.action:
          _print_service_actions(sanitize_input(args.service))
          sys.exit(1)

  And add, next to `action_completer` (~line 632):

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

  This is the same four-step sequence `action_completer` runs at cli.py:638-655 — reuse by
  copy, not by extracting a shared helper (the completer additionally mutates
  `_current_completion_context` and swallows every exception, so the shared core would be a
  3-line comprehension). `get_service_operations` uses `_BotocoreSessionContext`, which pops
  `AWS_PROFILE` and needs no credentials, and returns `[]` for an unknown service — hence the
  explicit unknown-service message before the listing.

  **(c) Parser epilog** (line 675, inside the `Examples:` block): add two lines,
  `  awsquery ec2  (uses the default action, describe-instances)` and
  `  awsquery s3 -- Name  (default action + column filter)`. Keep the existing first example
  line byte-identical — `tests/unit/test_cli_help_output.py:98` asserts on it — and keep the
  `Autocomplete Setup:` block after `Examples:` (asserted at line 131).

  Do NOT implement any post-parse substitution keyed on `args.action is None`: proven
  insufficient because argparse makes `ec2 -- InstanceId` and `ec2 InstanceId` identical
  post-parse. Do NOT demote an unrecognised second positional to a value filter.

  Constraints: flake8-docstrings requires docstrings on both new functions (D103 ignored but
  the repo style has them); line length 100; run `make format` before verifying.
  </action>
  <verify>
  <automated>python3 -m pytest tests/unit/test_cli_parser.py tests/unit/test_cli_flags.py tests/unit/test_cli_help_output.py tests/unit/test_cli_arg_processing.py -q && python3 -c "
import sys; sys.path.insert(0,'src')
from awsquery.cli import _inject_default_action as f
assert f(['ec2']) == ['ec2','describe-instances']
assert f(['ec2','--','InstanceId']) == ['ec2','describe-instances','--','InstanceId']
assert f(['-j','ec2','--','X']) == ['-j','ec2','describe-instances','--','X']
assert f(['--region','us-west-2','ec2']) == ['--region','us-west-2','ec2','describe-instances']
assert f(['ec2','describe-instances','--','X']) == ['ec2','describe-instances','--','X']
assert f(['ec2','prod']) == ['ec2','prod']
assert f(['budgets']) == ['budgets']
assert f(['']) == [''] and f([]) == [] and f(['--help']) == ['--help']
print('injector ok')" && make lint</automated>
  </verify>
  <done>
  - `_inject_default_action` exists, is pure, and satisfies every case in the verify command
  - `cli.py:752` passes `_inject_default_action(sys.argv[1:])` to `parse_known_args`; the call
    sits after `argcomplete.autocomplete(...)`; `sys.argv` is never mutated
  - The `cli.py:830` branch is split: no-service prints services on stdout and exits 0;
    service-with-no-default calls `_print_service_actions` and exits 1
  - `_print_service_actions` writes to stderr and prints an explicit unknown-service error
  - Two default-action examples added to the parser epilog; `test_cli_help_output.py` still passes
  - `make lint` clean
  </done>
</task>

<task type="auto">
  <name>Task 4: Curated-map validation, injector, flag pass-through and casing tests</name>
  <files>tests/unit/test_default_column_filters.py, tests/unit/test_cli_parser.py, tests/unit/test_cli_flags.py, tests/unit/test_security.py</files>
  <action>
  All test work goes through `@agent-test-writer`. Extend the four EXISTING files below — do
  NOT create `tests/unit/test_default_actions.py` or any other new file (CLAUDE.md forbids
  duplicate test files, and a grep of `tests/` found no existing coverage of this feature).

  **1. `tests/unit/test_default_column_filters.py` — new class `TestDefaultActionsMap`**, placed
  next to `TestYAMLConfigurationStructure` (line 326), which is already the home for
  data-validation tests that reach into botocore. This is the whole-map guard. Use
  `@pytest.mark.parametrize` over `sorted(load_default_actions().items())` — `parametrize` is
  the ONLY marker CLAUDE.md permits. Per entry assert:
    1. the service is in `Loader().list_available_services("service-2")`;
    2. the operation resolves **case-insensitively** in `model.operation_names` — match on
       `op.lower() == to_pascal_case(to_snake_case(action)).lower()`. A plain PascalCase match
       fails on acronyms: `to_pascal_case("list_saml_providers")` yields `ListSamlProviders`
       but botocore's real name is `ListSAMLProviders`. `shapes.py:70-84` already implements
       this fallback — copy the approach;
    3. `input_shape is None or not input_shape.required_members` — the `is None` guard is
       required, e.g. `sts:GetCallerIdentity` has no input shape at all and would otherwise
       raise `AttributeError: 'NoneType' object has no attribute 'required_members'`;
    4. `security.is_readonly_operation(action) is True`;
    5. `action == to_kebab_case(to_snake_case(action))` — pins the file as canonical kebab-case
       so the defensive normalisation in `_inject_default_action` never has to do real work;
    6. `to_snake_case(action) in load_default_filters()[service]` — every defaulted action has
       curated columns.
  Plus one non-parametrized test asserting
  `set(load_default_actions()) <= set(load_default_filters())`.
  Build the model **credential-free** via `botocore.loaders.Loader` + `botocore.model.ServiceModel`
  (see `<interfaces>`), NOT `boto3.client()` — the latter needs a region and sometimes
  credentials and would break CI. Cache the loader/model per service so the parametrized run
  does not reload 50 service models repeatedly.

  **2. `tests/unit/test_cli_parser.py` — new class `TestDefaultActionInjection`** (this file
  already owns separator-parsing behaviour). Pure-function tests on `_inject_default_action`
  with **zero mocks** — it takes a list and returns a list:
  `["ec2"] -> ["ec2","describe-instances"]`;
  `["ec2","--","InstanceId"] -> ["ec2","describe-instances","--","InstanceId"]`;
  `["ec2","--","InstanceId","State"]` injects and preserves both filters;
  `["-j","ec2","--","X"]` injects at index 2; `["--region","us-west-2","ec2"]` does not treat
  `us-west-2` as the service; `["-p","MaxResults=5","ec2"]` likewise; and unchanged for
  `["ec2","describe-instances","--","X"]`, `["ec2","prod"]`, `["budgets"]`, `[""]`, `[]`,
  `["--help"]`, `["--","ec2"]`.
  Then the equivalence tests: with **boto3 mocked only**, run `main()` for
  `["awsquery","ec2","--","InstanceId"]` and for
  `["awsquery","ec2","describe-instances","--","InstanceId"]` and assert
  `format_table_output` received identical column filters — this is the acceptance criterion
  that a post-parse implementation silently fails.

  **3. `tests/unit/test_cli_flags.py` — extend `TestCLIFlagHandling`**: flag/parameter
  pass-through on a defaulted action. `["awsquery","ec2","-j"]` produces JSON output for
  `describe_instances`; `["awsquery","-d","ec2"]` emits the `Using default action` line on
  **stderr**; `["awsquery","ec2","-p","MaxResults=5"]` reaches `execute_aws_call` with the
  parameter. Also assert `validate_readonly` is reached with the **kebab** spelling for a
  defaulted action.

  **4. `tests/unit/test_security.py` — extend `TestReadOnlyOperations`**: pin the casing trap
  with a direct pair — `is_readonly_operation("describe-instances") is True` and
  `is_readonly_operation("describe_instances") is False` (plus `list-buckets` /
  `list_buckets`). A test, not a comment, is what keeps a future contributor from
  "normalising" the YAML to snake_case.

  Style constraints, enforced (CLAUDE.md): no `@pytest.mark.*` except `parametrize`; mock
  `boto3` ONLY — never patch `get_default_action`, `_inject_default_action`,
  `filter_resources`, or `determine_column_filters`, the functions under test; at most two
  nested `with patch()` contexts — the existing `test_cli_parser.py` tests already sit at three
  and must NOT be used as the template, prefer decorator-stacked `@patch` as
  `test_cli_flags.py` does; no docstring that restates the test name; no TDD placeholder
  comments.
  </action>
  <verify>
  <automated>python3 -m pytest tests/unit/test_default_column_filters.py tests/unit/test_cli_parser.py tests/unit/test_cli_flags.py tests/unit/test_security.py -v && grep -rn "@pytest.mark." tests/unit/ tests/integration/ | grep -v "parametrize" | (! grep .) && echo no-banned-markers</automated>
  </verify>
  <done>
  - `TestDefaultActionsMap` parametrizes over all 50 entries and all six per-entry assertions
    pass, using `botocore.loaders.Loader` with no boto3 client and no credentials
  - `TestDefaultActionInjection` covers all listed argv shapes with zero mocks, plus the
    `ec2 -- InstanceId` == `ec2 describe-instances -- InstanceId` equivalence via `main()`
  - Flag/parameter pass-through and the debug line are asserted for a defaulted action
  - `is_readonly_operation` kebab-vs-snake asymmetry is pinned by a test
  - No new test files; no markers other than `parametrize`; no over-mocking
  </done>
</task>

<task type="auto">
  <name>Task 5: Rewrite the vacuously-green integration test at test_end_to_end.py:889</name>
  <files>tests/integration/test_end_to_end.py</files>
  <action>
  `test_main_function_service_listing` (line 889) sets `sys.argv = ["awsquery","ec2"]` and
  guards every assertion behind `if "Available services:" in output:`. After this change that
  string is no longer emitted for a service-given invocation, so **the test goes green
  vacuously while `main()` actually proceeds to attempt AWS work** under a partially-mocked
  `boto3.Session` — a silent hang or credential-error risk in CI, and zero real coverage.
  It must be rewritten, not left "still passing".

  Replace it with two focused tests (this task is done by `@agent-test-writer`):

  - `awsquery` with NO arguments (`sys.argv = ["awsquery"]`) still prints
    `Available services:` on **stdout** and exits 0. Assert unconditionally — no
    `if ... in output` guard. Assert on the captured `SystemExit` code rather than patching
    `sys.exit` to a Mock, so execution actually stops where it should.
  - `awsquery budgets` (a service deliberately absent from `default_actions.yaml` because
    `DescribeBudgets` requires `AccountId`) writes the action listing to **stderr** — capture
    stderr, not stdout — and exits non-zero. Assert the `No default action configured for
    'budgets'` prefix and that at least one kebab-case action line is present.

  Leave `test_missing_service_action_edge_cases` (line 629) alone: `["awsquery","","describe-instances"]`
  is verified safe — the injector finds `""` as the service candidate, `get_default_action("")`
  returns `None`, no injection happens, and `not args.service` still fires.

  Mock `boto3` only. No markers. No docstring that restates the test name.
  </action>
  <verify>
  <automated>python3 -m pytest tests/integration/test_end_to_end.py -v && ! grep -n 'if "Available services:" in output' tests/integration/test_end_to_end.py</automated>
  </verify>
  <done>
  - `test_main_function_service_listing` no longer exists in its guarded form; the
    `if "Available services:" in output` conditional is gone from the file
  - A no-argument test asserts `Available services:` on stdout and exit code 0 unconditionally
  - A `budgets` test asserts the action listing on stderr and a non-zero exit code
  - `test_missing_service_action_edge_cases` is unchanged and still passes
  - The integration suite completes without attempting a real AWS call
  </done>
</task>

<task type="auto">
  <name>Task 6: Document the default-action shortcut in the README</name>
  <files>README.md</files>
  <action>
  Three README edits (line numbers from the current file; locate by heading text if they drift).

  1. **Feature bullets (~line 30)**, next to the existing `**Default Column Filters**` bullet:
     add `- **Default Actions**: A bare service name runs its curated default operation —
     `awsquery ec2` == `awsquery ec2 describe-instances`` plus one bare-service example
     (`awsquery s3 -- Name`) so the shortcut is discoverable above the fold.

  2. **New `### Default Actions Configuration` subsection** under `## Configuration`, as a
     sibling immediately after `### Default Filters Configuration` (line 293). Cover: bare
     `awsquery <service>` runs the curated default; the map lives in
     `src/awsquery/default_actions.yaml` as a flat `service: action` map; **values are
     kebab-case** (state that this is required, because the ReadOnly validator only recognises
     kebab spellings — a snake_case value turns the command into an interactive prompt);
     adding a service is a one-line YAML edit; the two rules an entry must satisfy (ReadOnly,
     no required parameters); and that a service with no entry prints its available actions on
     stderr and exits non-zero, while `awsquery` with no service still lists services and exits
     0. Include the shortcut table:

     | Command | Equivalent to |
     | `awsquery ec2` | `awsquery ec2 describe-instances` |
     | `awsquery s3` | `awsquery s3 list-buckets` |
     | `awsquery ec2 -- InstanceId` | `awsquery ec2 describe-instances -- InstanceId` |

     Show a short YAML snippet (3-4 entries from the real file, kebab-case).

  3. **Additive column filters table (lines 455-462)**: add one row so the shortcut is visible
     where columns are explained — `awsquery ec2 -- +InstanceId` → "defaults + `InstanceId`,
     using the `ec2` default action".

  Document only what this issue ships. Do NOT document the deferred items (heuristic
  inference, default parameters, `~/.awsquery/` user overrides). No AI attribution anywhere.
  </action>
  <verify>
  <automated>grep -q "Default Actions Configuration" README.md && grep -q "default_actions.yaml" README.md && grep -q "awsquery ec2 -- +InstanceId" README.md && grep -qi "kebab" README.md && echo readme-ok</automated>
  </verify>
  <done>
  - A `**Default Actions**` feature bullet and a bare-service example appear above the fold
  - A `### Default Actions Configuration` subsection sits beside the Default Filters section and
    documents the file location, kebab-case requirement, the two entry rules, the shortcut
    table, and both fallback behaviours
  - The additive-columns table has a default-action row
  - No deferred feature is documented as shipped
  </done>
</task>

</tasks>

<verification>
Run all three gates from the project environment (Docker image or a venv with the project's
dependencies). **The research agent could NOT run the suite — its interpreter lacked `boto3`,
`botocore`, `argcomplete` and `pytest` — so the pre-existing state of the suite is
green-until-proven-otherwise, not verified green. Actually run these; do not assume.**

- `make test` — full suite (`python3 -m pytest tests/ -v`), all tests, no marker selection
- `make lint` — `flake8 src/ tests/ --count --statistics --show-source` and `pylint src/awsquery`
- `make format-check` — `black --check --diff src/ tests/` and `isort --check-only --diff src/ tests/`
  (run `make format` first if it reports diffs)
- Coverage gate: `pytest.ini` enforces an 80% minimum — confirm `make test` does not fail on it

Single test runner: this repo uses pytest exclusively (`Makefile:39-61` and
`.github/workflows/test.yml:41` both invoke `python -m pytest`). There is no unittest CI path,
so no dual-runner gate applies.

Packaging spot-check (cannot be covered by unit tests, which read the source tree):
`python3 -m build && unzip -l dist/*.whl | grep default_actions.yaml`
</verification>

<success_criteria>
Maps 1:1 to ISSUE.md's acceptance criteria, with the two research-driven corrections applied
(separate YAML file instead of a `default_action:` key; kebab-case values):

- `src/awsquery/default_actions.yaml` carries 50 curated `service: kebab-action` entries, parses
  via `load_default_actions()`, and is registered in `pyproject.toml` package data
- `default_filters.yaml` is untouched and still parses via `load_default_filters()`
- `config.get_default_action(service)` returns the configured action, is case-insensitive in the
  same way as `get_default_columns`, and returns `None` for unconfigured/unknown/empty services
- `awsquery ec2` produces the same output as `awsquery ec2 describe-instances`
- `awsquery s3` produces the same output as `awsquery s3 list-buckets`
- `awsquery ec2 -- InstanceId` produces the same output as
  `awsquery ec2 describe-instances -- InstanceId` (the criterion a post-parse implementation
  silently fails), and flags (`-j`, `-d`, `-p`, `--region`) apply to the defaulted action
- The defaulted action passes through `validate_readonly` in its kebab form and never triggers
  `prompt_unsafe_operation`; a non-ReadOnly default would be rejected like any other action
- Default column filters from `default_filters.yaml` still apply to the defaulted action
- `awsquery budgets` (no curated default) lists that service's ReadOnly actions on **stderr**
  and exits non-zero
- `awsquery` with no arguments still lists available services on stdout and exits 0
- Only a `debug_print` announces the chosen default — stdout and stderr stay clean on normal runs
- Tests cover: default resolution, unconfigured-service fallback, filter/flag pass-through,
  readonly validation of the defaulted action, and a whole-map validation asserting every entry
  is a real botocore operation with zero required members, ReadOnly, and canonical kebab-case
- `tests/integration/test_end_to_end.py` no longer contains a vacuously-guarded service-listing
  assertion
- README documents the shortcut and the `default_actions.yaml` config file
- `make test`, `make lint`, and `make format-check` all pass, run for real in the project
  environment
</success_criteria>
