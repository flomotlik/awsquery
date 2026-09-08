---
id: ty5dx
title: Add per-service default actions so awsquery ec2 runs without an action
status: done
priority: medium
labels:
- enhancement
- cli
remote:
- source: github
  id: '18'
  url: https://github.com/flomotlik/awsquery/issues/18
---

## Context

Today `awsquery ec2` (service given, no action) falls into the `if not args.service or not args.action` branch in `src/awsquery/cli.py:830` and prints the full list of AWS services — which ignores the service the user just typed and is not useful.

`awsinfo` treats the bare service name as a shortcut for its most common read operation. We want the same: `awsquery ec2` should behave as `awsquery ec2 describe-instances`, `awsquery s3` as `awsquery s3 list-buckets`, and so on.

The pieces to build on already exist: `src/awsquery/config.py` loads and caches `src/awsquery/default_filters.yaml` (`load_default_filters`), and `get_default_columns(service, action)` already resolves per-service/per-action output columns from it. A default *action* is the missing counterpart to the default *columns*.

## Scope

**1. Curated YAML map for default actions**

- Add a per-service `default_action:` key to the existing `default_filters.yaml` structure (sibling of the per-action entries), e.g.:

  ```yaml
  ec2:
    default_action: describe_instances
    describe_instances:
      columns:
      - InstanceId$
      ...
  ```

- Hand-curate the mapping for the common services (ec2, s3, rds, lambda, ecs, eks, iam, cloudformation, dynamodb, sqs, sns, elbv2, autoscaling, cloudwatch, logs, ssm, secretsmanager, route53, acm, …). Curated only — no botocore heuristic inference in this issue.
- Add a `get_default_action(service)` accessor in `src/awsquery/config.py`, matching the existing `get_default_columns` shape (normalized/lowercased lookup, `debug_print` on hit and miss, returns `None` when unset).

**2. CLI wiring**

- In `main()` (`src/awsquery/cli.py`), when `args.service` is set and `args.action` is empty, resolve the default action via `get_default_action(service)` and continue as if the user had typed it.
- The resolved action must go through the normal path unchanged: `validate_readonly` security validation, parameter requirements / multi-level resolution, default column filters, and any user-supplied `--` filters and flags. `awsquery ec2 -- InstanceId` must work exactly like `awsquery ec2 describe-instances -- InstanceId`.
- Emit a `debug_print` recording which default action was chosen.
- The default action name carries **no default parameters** — it is only the operation name. Output shaping stays with the existing `default_filters.yaml` columns.

**3. Fallback when no default is configured**

- `awsquery <service>` for a service with no `default_action:` prints the available actions **for that service** to stderr and exits non-zero — replacing today's full-service-list behavior for this case.
- `awsquery` with no service at all keeps its current behavior (print available services, exit 0).

**4. Docs and tests**

- Update README/help text to document the shortcut and how to configure `default_action:`.
- Tests exercise the real implementation with only boto3 mocked, per the repo's testing rules — no pytest markers, no over-mocking.

## Acceptance Criteria

- [ ] `default_filters.yaml` carries a `default_action:` entry for each curated service, and the file still parses cleanly via `load_default_filters()`
- [ ] `config.get_default_action(service)` returns the configured action, is case/format-insensitive in the same way as `get_default_columns`, and returns `None` for unconfigured services
- [ ] `awsquery ec2` produces the same output as `awsquery ec2 describe-instances`
- [ ] `awsquery s3` produces the same output as `awsquery s3 list-buckets`
- [ ] User filters and flags apply to the defaulted action (`awsquery ec2 -- InstanceId` == `awsquery ec2 describe-instances -- InstanceId`)
- [ ] The defaulted action passes through `validate_readonly` — a non-ReadOnly default would be rejected like any other action
- [ ] Default column filters from `default_filters.yaml` still apply to the defaulted action
- [ ] `awsquery <service-without-default>` lists that service's actions on stderr and exits non-zero
- [ ] `awsquery` with no arguments still lists available services and exits 0
- [ ] Tests cover: default resolution, unconfigured-service fallback, filter/flag pass-through, and readonly validation of the defaulted action
- [ ] README documents the shortcut and the `default_action:` config key
- [ ] `make test`, `make lint`, and `make format-check` pass
