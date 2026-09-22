# awsquery — complete reference for AI agents and LLM tool calls

awsquery runs any read-only AWS API operation through boto3 and filters the response down to the
rows and columns you asked for. One command replaces `aws ... --query` JMESPath plus `jq`: filters
are plain substrings, not a query language.

This document is the full contract. It is printed by `awsquery --docs` and needs no network access.

## Invocation

```
awsquery [FLAGS] SERVICE [ACTION] [VALUE_FILTERS...] [-- COLUMN_FILTERS...]
```

If awsquery is not installed, run it with no install step:

```
uvx awsquery ec2 describe-instances
```

`SERVICE` is an AWS service id (`ec2`, `s3`, `iam`, `cloudformation`, ...). `ACTION` is a
kebab-case operation (`describe-instances`, `list-buckets`). Omit `ACTION` to use the curated
default action for that service (`awsquery ec2` == `awsquery ec2 describe-instances`).

## Start here: discovery without AWS credentials

These four flags make no AWS API call, need no credentials and no region, and return in well under a
second. Use them to plan a query instead of guessing field names and failing against the live API.

| Command | Answers |
| --- | --- |
| `awsquery --list-services` | which services exist |
| `awsquery ec2 --list-actions` | which read-only operations that service has |
| `awsquery --schema ec2 describe-instances` | which parameters it takes and every field it can return |
| `awsquery --schema ec2` | the same, for that service's default action |
| `awsquery --docs` | this document |

Add `-j` to `--list-services`, `--list-actions` or `--schema` for JSON. `--docs` is always Markdown.
`--list-services` and `--list-actions` follow `--format`: a JSON array under `json`, one bare name
per line under `csv`, `tsv` and `ndjson`. Running `awsquery` with no service at all lists the
services the same way.

`--schema` is the one to reach for. It reads botocore's service model, so it lists **every** field
the API can return, with types — including fields absent from your account's current data:

```
$ awsquery --schema ec2 describe-instances
ec2 describe-instances (readonly, paginated)

Input parameters:
  DryRun                         boolean         optional
  Filters                        list            optional
  InstanceIds                    list            optional
  MaxResults                     integer         optional
Required: none

Default columns: Tags.Name$ InstanceId$ InstanceType$ State.Name$

Output fields (213):
  Instances.InstanceId           string
  Instances.InstanceType         string
  Instances.State.Name           string
  ...
```

**Turning a schema path into a column filter.** Paths are relative to the extracted data field, so
they are often usable as-is: `iam list-roles` reports `RoleName`, and `-- RoleName$` works. But where
a path crosses a *further* list level, that level carries an index at runtime — `ec2
describe-instances` reports `Instances.State.Name` while the real flattened key is
`Instances.0.State.Name`, so the literal path matches nothing.

Pick the filter from the shape of the path:

| Schema path | Use | Why |
| --- | --- | --- |
| `RoleName` (no dots) | `^RoleName$` | exact — selects that column and nothing else |
| `Instances.State.Name` (crosses a list) | `State.Name$` | suffix anchor ignores the `Instances.0.` prefix |
| anything below one node | `^Instances` | matches everything under it |

`$` alone is the safe fallback when you are unsure, but it is a *suffix* match, so it also catches
same-named fields nested elsewhere: on `rds describe-db-instances`, `DBInstanceIdentifier$` returns
both `DBInstanceIdentifier` and `PendingModifiedValues.DBInstanceIdentifier`. When the schema path
has no dots, `^…$` gives you exactly the one column.

`^path$` only matches when the path has no list level above it — which is why the curated defaults
in `default_filters.yaml` are `$`-anchored leaf names: that form works regardless of nesting, at the
cost of occasionally pulling in a same-named nested sibling.

**Tags are special.** AWS tag lists are converted at runtime into `Tags.<Key>` columns, so a tag
becomes `Tags.Name$`, `Tags.Environment$` and so on. The schema cannot know your tag keys; it only
shows `Instances.Tags.Key` and `Instances.Tags.Value`.

`--schema -j` returns:

```json
{"service": "ec2", "action": "describe-instances", "operation": "DescribeInstances",
 "readonly": true, "paginated": true, "data_field": "Reservations",
 "input": {"required": [], "parameters": {"InstanceIds": "list", "MaxResults": "integer"}},
 "default_columns": ["Tags.Name$", "InstanceId$"],
 "output_fields": {"Instances.InstanceId": "string", "Instances.State.Name": "string"},
 "filter_hint": "Filter columns by the trailing segments with a $ anchor ..."}
```

### `--schema` vs `-k/--keys`

- `--schema` — what the API **can** return. Offline, instant, complete, no credentials.
- `-k` / `--keys` — what your account **did** return. Makes a real API call, so it needs
  credentials and a region, and it only shows fields that are populated in the resources that
  exist right now.

Prefer `--schema` when choosing columns. Use `-k` only to inspect actual live data.

`-k` honours `--format`: `{"keys": [...]}` under `json`, one JSON string per line under `ndjson`, a
`key` column under `csv`/`tsv`, and the indented list under `table`. `--limit` does not apply to it.

## Filter grammar

Everything after the action is a filter. The `--` separators decide what each group filters.

**Single-level call** (the operation needs no extra parameters):

```
awsquery SERVICE ACTION [value filters] -- [column filters]
```

- **Value filters** match against any field's *contents* **and its name**. All of them must match
  (AND). Because names are searched too, a field name used as a value filter matches every
  resource — `awsquery ec2 describe-instances InstanceId` returns everything, not nothing.
- **Column filters** match against *field names*, and select which columns appear.

```bash
awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId
#                                ^^^^^^^^    ^^^^^^^^^^^^^^^^^^^^^^^^^
#                                values      columns
```

**Multi-level call** (the operation requires a parameter awsquery must resolve first, e.g.
`describe-stack-events` needs a `StackName`): awsquery calls a list operation, picks resources from
it, then calls the target operation for each. A third group appears, and the groups shift meaning:

```
awsquery SERVICE ACTION [resource filters] -- [value filters] -- [column filters]
```

- **Resource filters** pick which resources from the *first* (list) call get expanded.
- **Value filters** filter the *final* results.
- **Column filters** select columns, as always.

```bash
awsquery cloudformation describe-stack-events prod -- CREATE_FAILED -- Timestamp ResourceStatus
#                                             ^^^^    ^^^^^^^^^^^^^    ^^^^^^^^^^^^^^^^^^^^^^^
#                                        which stacks  which events     which columns
```

### Matching rules

All matching is **case-insensitive substring** by default, with optional anchors:

| Pattern | Matches |
| --- | --- |
| `prod` | contains: `production`, `my-prod-app` |
| `^prod` | starts with: `production`, `prod-web` |
| `prod$` | ends with: `my-prod`, `dev-prod` |
| `^prod$` | exactly `prod` |

For column filters, anchors apply to the **full flattened key** (`Instances.0.State.Name`), not to
the displayed header. Prefer `Name$`-style suffix anchors for nested fields.

These are anchors, not regular expressions — no `.*`, no character classes. A `.` is a literal dot,
which is also the path separator in flattened field names (`State.Name`, `Tags.Name`).

### Column defaults and additive columns

Many service/action pairs have curated default columns. Supplying any column filter **replaces**
those defaults. Prefix a column with `+` to merge with them instead:

```bash
awsquery ec2 describe-instances                    # curated defaults
awsquery ec2 describe-instances -- InstanceId      # only InstanceId
awsquery ec2 describe-instances -- +InstanceId     # defaults plus InstanceId
```

One `+` anywhere in the column group switches the whole group to additive mode. The active defaults
are reported on stderr and listed by `--schema`.

## Flags

| Flag | Effect |
| --- | --- |
| `-j`, `--json` | JSON output; identical to `--format json` |
| `--format FMT` | `table` (default), `json`, `csv`, `tsv`, `ndjson` |
| `--limit N` | truncate output to N resources; notes the truncation on stderr |
| `-k`, `--keys` | list the field names present in the live response; follows `--format` |
| `--schema` | print the operation's input/output contract, no AWS call |
| `--list-services` | list every supported service, no AWS call |
| `--list-actions` | list a service's read-only actions, no AWS call |
| `--docs` | print this reference, no AWS call |
| `-p`, `--parameter K=V` | pass a parameter to the API; repeatable |
| `-i`, `--input HINT` | steer multi-level resolution (see below) |
| `--region`, `--profile` | AWS session selection |
| `-d`, `--debug` | verbose trace on stderr |
| `--allow-unsafe` | permit a non-read-only operation without prompting |

## Output formats and token cost

`table` and `json` are shaped for humans. For anything you are going to read as an LLM, `csv` is
roughly a third of the tokens — measured on 50 rows by 5 columns: grid table ~2340 tokens,
`json` (indented) ~2440, `csv` ~790.

- `csv` / `tsv` — header row plus one line per resource. Cheapest, and faithful: values are not
  truncated, falsy values are preserved, repeated values keep their order. Use it by default.
  Cells are text, so booleans render as `True`/`False` — use `ndjson` if you need typed values.
- `ndjson` — one compact JSON object per line, no envelope, native JSON types. Use when you need
  typed values or want to stream rows.
- `json` — `{"results": [...]}`, indented, native types, one object per resource. Use when a
  downstream tool expects that envelope.
- `table` — aligned grid with borders, and the only **lossy** format: long values are truncated,
  repeated values are deduplicated and summarised as `(+N more)`, falsy cells render blank and
  all-blank rows are dropped. It is for showing a human. Never parse it.

`csv`, `tsv`, `ndjson` and `json` all emit one row per resource, so a row count is a resource
count. `table` does not.

**An empty result set produces no output at all** under `csv`, `tsv` and `ndjson` — not even a
header row, because column names are derived from the data. Only `json` still returns a body
(`{"results": []}`). Exit status is 0 either way, so check the exit code, not whether stdout is
empty, and prefer `--format json` when a parser needs a document even for no matches.

Always combine a format with explicit column filters and `--limit`. Selecting four columns out of
213 is the difference between a usable answer and a context overflow:

```bash
awsquery --format csv --limit 50 ec2 describe-instances prod -- InstanceId Tags.Name State.Name
```

## Streams, exit codes and errors

- **stdout** carries data only. Notices ("Using default columns: ...") and all errors go to
  **stderr**, so stdout stays parseable.
- Empty results are a success: exit 0 with no rows.

| Code | Meaning |
| --- | --- |
| 0 | success, including an empty result set |
| 1 | general or unexpected error |
| 2 | usage error, unknown service or action, or an unsafe operation refused non-interactively |
| 3 | AWS API error |
| 4 | credentials, region or authentication failure |

Under `--format json` and `--format ndjson`, errors are additionally emitted to stderr as one
compact JSON object, with a `hint` naming the next command to run where one applies:

```json
{"error": {"code": 2, "type": "UnknownService", "message": "Unknown service 'ec3'",
           "hint": "Run: awsquery --list-services"}}
{"error": {"code": 4, "type": "AccessDeniedException", "message": "...",
           "hint": "Credentials are valid but lack permission for this operation; try a different profile or role"}}
```

Exit 4 covers both halves of the identity problem, and the hint says which: re-authenticate, or use an
identity with more permission. Retrying either is pointless, which is why neither is a code 3.

A successful run that simply has nothing to report uses a different key, so branching on the
presence of `error` is safe:

```json
{"notice": {"code": 0, "type": "EmptyResult", "message": "No data to extract keys from in successful response"}}
```

## Safety model

awsquery only runs read-only operations. Operations are classified by prefix (`List`, `Get`,
`Describe`, `Search`, `Lookup`, `BatchGet`, ...). Anything else is refused.

In a non-interactive context — no TTY on stdin, or `AWSQUERY_NON_INTERACTIVE=1` — a non-read-only
operation is **refused immediately with exit 2**. It never prompts and never blocks. Pass
`--allow-unsafe` to proceed deliberately.

If you are driving awsquery from an agent loop, set `AWSQUERY_NON_INTERACTIVE=1` so this is
guaranteed regardless of how stdin is wired.

## Credentials and region

awsquery uses the standard boto3 chain: environment variables, `~/.aws/credentials`, SSO sessions,
instance and container roles. `--profile` and `--region` override.

**Region gotcha:** boto3 honours `AWS_DEFAULT_REGION`. awsquery additionally falls back to
`AWS_REGION` when `AWS_DEFAULT_REGION` is unset, so either works here — but prefer
`AWS_DEFAULT_REGION` or an explicit `--region` for portability.

Missing region or credentials exits 4. Nothing about awsquery is sandboxed: it acts as whatever
identity your environment provides.

## Parameters (`-p`)

```bash
awsquery ec2 describe-instances -p MaxResults=20
awsquery ec2 describe-instances -p InstanceIds=i-1234567890abcdef0,i-0987654321fedcba0
awsquery ssm describe-parameters -p ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu
```

- Simple: `Key=Value`. Lists: `Key=V1,V2,V3`.
- Multiple objects: separate with `;` — `LookupAttributes=AttributeKey=EventName,AttributeValue=Login;AttributeKey=Username,AttributeValue=admin`
- Numbers and booleans are converted automatically.
- `-p` is repeatable and propagates into the list operation of a multi-level call.
- `--schema` tells you which parameter names and types are valid.

## Multi-level hints (`-i`)

When awsquery resolves a missing parameter it guesses which list operation to call and which field
to extract. `-i` overrides the guess:

```
-i [service:][function]:[field]:[limit]
```

```bash
awsquery cloudformation describe-stack-resources -i list-sta prod   # pick the list operation
awsquery elbv2 describe-tags -i desc-clus:clusterarn prod           # operation + field
awsquery ecs describe-tasks -i :clusterarn                          # field only
awsquery ssm get-parameters -i ::5                                  # cap resources at 5
awsquery s3 list-objects-v2 -i ::0                                  # uncapped
awsquery ssm describe-instance-patch-states -i ec2:desc-inst:instanceid prod   # cross-service
```

- Any component may be omitted; the colons hold the positions.
- Function names use the same smart matching as completion: `desc-inst` finds `describe-instances`.
- The default resource cap is 10. `::0` removes it — expect one API call per resource.
- `-i ::N` caps resources fed into resolution. `--limit N` truncates the printed resources. They are
  independent, and they treat `0` differently: `-i ::0` means *unlimited*, while `--limit 0` means
  *zero rows* and prints nothing. Omit `--limit` for no row limit.

## Recipes

```bash
# What can I even ask for?
awsquery --list-services
awsquery ec2 --list-actions
awsquery --schema ec2 describe-instances -j

# Cheapest useful query: pick columns, cap rows, csv
awsquery --format csv --limit 50 ec2 describe-instances -- InstanceId Tags.Name State.Name

# Find production web instances, exact state column
awsquery ec2 describe-instances prod web -- Tags.Name$ State.Name$ InstanceId$

# Buckets whose name contains "backup"
awsquery --format csv s3 list-buckets backup -- Name CreationDate

# Failed events for production stacks (multi-level: stacks, then events)
awsquery cloudformation describe-stack-events prod -- CREATE_FAILED -- Timestamp ResourceStatus

# Default columns plus one extra
awsquery ec2 describe-instances -- +VpcId

# Cross-service: resolve EC2 instance ids, then query SSM patch state
awsquery ssm describe-instance-patch-states -i ec2:desc-inst:instanceid prod

# Service default action, JSON envelope
awsquery -j iam

# Diagnose a query that returned nothing
awsquery -d ec2 describe-instances prod
```

## Failure modes and what to do

| Symptom | Cause | Next step |
| --- | --- | --- |
| exit 4, "You must specify a region" | no region resolved | pass `--region`, or set `AWS_DEFAULT_REGION` |
| exit 4, auth failure | missing or expired credentials | refresh SSO, or pass `--profile` |
| exit 2, unknown service | typo in the service id | `awsquery --list-services` |
| exit 2, no default action | that service has no curated default | `awsquery SERVICE --list-actions` |
| exit 2, unsafe operation refused | operation is not read-only | choose a `describe-`/`list-`/`get-` operation |
| empty table, exit 0 | value filters matched nothing | drop filters, then re-add one at a time; `-d` shows the raw response |
| exit 2, "No resources found matching resource filters" | a multi-level call's *resource* filters matched no resource to expand | widen the filters before the first `--`, or name the resource with `-i` |
| a column you expected is missing | column filter did not match any field name | `awsquery --schema SERVICE ACTION` for the real field paths |
| far too much output | no column filters | select columns, add `--limit`, use `--format csv` |

## Notes for agents

- Run `--schema` before a query you are unsure about. It is free and it removes the guesswork that
  causes most failed calls.
- Column filters match field **names** only; value filters match names **and** contents. Mixing
  them up is the most common mistake, and it fails silently: a field name used as a value filter
  matches every resource, so you get a full table that looks filtered. Put column names after `--`.
- Set `AWSQUERY_NON_INTERACTIVE=1` so awsquery can never wait on input.
- Parse stdout only; stderr carries notices that are not part of the data.
- Prefer one specific query over fetching everything and filtering yourself — the filters run before
  the output is rendered, so they save tokens, not just typing.
