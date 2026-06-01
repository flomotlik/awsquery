---
id: e1bzl
title: Fix remaining 15 broken $-suffix entries surfaced by audit
status: done
priority: medium
labels:
- bug
- filters
remote:
- source: github
  id: '14'
  url: https://github.com/flomotlik/awsquery/issues/14
---

## Summary

Follow-up to sue5t. The shape-aware audit script (`scripts/audit_default_filters.py`) introduced in that issue surfaced 15 additional `$`-suffix entries in `default_filters.yaml` that don't match any post-transform field name. All are list-of-primitive fields where the `$` anchor prevents matching against the flattened `Foo.0..N` keys.

## Broken entries

All 15 entries fail with the same root cause (anchored against a name that becomes `<name>.<index>` after flattening). Uniform fix: drop the `$` so the pattern becomes a contains-match. The contains-match captures every flattened index for that field.

| Service / Operation                                  | Entry                  | Line  | Diagnosis                                  |
| :--------------------------------------------------- | :--------------------- | ----: | :----------------------------------------- |
| `batch.describe_compute_environments`                | `instanceTypes$`       |  386  | list-of-primitive (deep nesting)           |
| `ce.get_cost_and_usage`                              | `Keys$`                | (~)   | list-of-primitive at `Groups.Keys.0..N`    |
| `cloudwatch.list_metrics`                            | `OwningAccounts$`      |  686  | list-of-primitive                          |
| `ec2.describe_vpc_endpoints`                         | `SubnetIds$`           | 1049  | list-of-primitive                          |
| `elasticbeanstalk.describe_applications`             | `ConfigurationTemplates$` | 1368  | list-of-primitive                          |
| `elasticbeanstalk.describe_applications`             | `Versions$`            | 1373  | list-of-primitive                          |
| `kafka.list_configurations`                          | `kafkaVersions$`       | 1832  | list-of-primitive                          |
| `route53.get_hosted_zone`                            | `NameServers$`         | 2288  | list-of-primitive at `DelegationSet.NameServers.0..N` |
| `s3.get_bucket_cors`                                 | `AllowedOrigins$`      | 2333  | list-of-primitive                          |
| `s3.get_bucket_cors`                                 | `AllowedMethods$`      | 2334  | list-of-primitive                          |
| `s3.get_bucket_cors`                                 | `AllowedHeaders$`      | 2335  | list-of-primitive                          |
| `s3.get_bucket_cors`                                 | `ExposeHeaders$`       | 2336  | list-of-primitive                          |
| `s3.get_bucket_notification_configuration`           | `Events$`              | 2361  | list-of-primitive                          |
| `ssm.get_parameters`                                 | `InvalidParameters$`   | 2645  | list-of-primitive                          |
| `ssm.get_parameters`                                 | `Parameters$`          | 2646  | list-of-objects; would match every column  |

## Scope

- `src/awsquery/default_filters.yaml` — single mechanical edit: strip trailing `$` from the 15 lines above.
- `scripts/audit_default_filters.py` — no change; it already classifies these correctly.
- Tests — re-run existing `test_audit_default_filters` (Task 7 of sue5t) and confirm the in-scope-after-fix set is empty.

## Special case: `ssm.get_parameters Parameters$`

Dropping `$` makes `Parameters` a contains-match — but the SSM response root is `Parameters: [...]`, so every flattened column begins with `Parameters.`. The contains-match matches all of them, effectively disabling the filter for that operation. Two options:

1. **Drop `$` anyway** — uniform with the other 14. Auto-column selection takes over; user sees a wide table by default. Same outcome as deleting the entry.
2. **Delete the entry** — explicit acknowledgment that defaults can't meaningfully filter this operation. Cleaner.

Plan picks option 2 (delete) for `Parameters$` only; option 1 (drop `$`) for all 14 others.

## Acceptance Criteria

- [ ] 14 entries: trailing `$` stripped in `default_filters.yaml`
- [ ] `ssm.get_parameters Parameters$` line deleted (kept `InvalidParameters` and the other 4 entries in that block)
- [ ] `python3 scripts/audit_default_filters.py` reports `Broken: 0` for the fixed set (the gate test from sue5t passes)
- [ ] `make test` green
- [ ] No grammar changes, no new module, no behavior changes elsewhere

## Inherited decisions (from sue5t CONTEXT.md, do not re-litigate)

D5 (static shape-aware audit), D7 (no YAML restructure, in-place edits only). Decisions D1–D4 and D6 are unrelated to this follow-up.
