---
slug: e1bzl-fix-remaining-15-broken-suffix-entries-surfaced-by-audit
stage: plan
research: (inherited from sue5t — audit script is the research)
generated: 2026-06-01
---

<strategy>
Mechanical YAML edit. 14 entries lose their trailing `$` (becomes contains-match against flattened `Foo.0..N` keys). 1 entry (`ssm.get_parameters Parameters$`) is deleted because contains-match would degenerate to "all columns". Validated by re-running the existing sue5t-introduced audit script + gate test.

No new code paths, no new files, no behavior change in the filter parser. The fix lives entirely in `default_filters.yaml`.
</strategy>

<tasks>

<task type="auto" id="1">
  <title>Strip $ from 14 list-of-primitive entries</title>
  <files>src/awsquery/default_filters.yaml</files>
  <action>
Edit `src/awsquery/default_filters.yaml`. Find each of the following 14 lines and remove only the trailing `$`. Leave indentation, dash, and field name unchanged. Do NOT reorder or restructure.

| Service operation block               | Edit                                                |
| :------------------------------------ | :-------------------------------------------------- |
| `batch.describe_compute_environments` | `- instanceTypes$` → `- instanceTypes`              |
| `ce.get_cost_and_usage`               | `- Keys$` → `- Keys`                                |
| `cloudwatch.list_metrics`             | `- OwningAccounts$` → `- OwningAccounts`            |
| `ec2.describe_vpc_endpoints`          | `- SubnetIds$` → `- SubnetIds`                      |
| `elasticbeanstalk.describe_applications` | `- ConfigurationTemplates$` → `- ConfigurationTemplates` |
| `elasticbeanstalk.describe_applications` | `- Versions$` → `- Versions`                     |
| `kafka.list_configurations`           | `- kafkaVersions$` → `- kafkaVersions`              |
| `route53.get_hosted_zone`             | `- NameServers$` → `- NameServers`                  |
| `s3.get_bucket_cors`                  | `- AllowedOrigins$` → `- AllowedOrigins`            |
| `s3.get_bucket_cors`                  | `- AllowedMethods$` → `- AllowedMethods`            |
| `s3.get_bucket_cors`                  | `- AllowedHeaders$` → `- AllowedHeaders`            |
| `s3.get_bucket_cors`                  | `- ExposeHeaders$` → `- ExposeHeaders`              |
| `s3.get_bucket_notification_configuration` | `- Events$` → `- Events`                       |
| `ssm.get_parameters`                  | `- InvalidParameters$` → `- InvalidParameters`      |

Verify each edit by re-grepping for `$` on those exact field names — must return zero matches after the edit.
  </action>
  <verify>
```bash
cd /workspace/.worktrees/e1bzl-fix-remaining-15-broken-suffix-entries-surfaced-by-audit
grep -nE -- "- (instanceTypes|Keys|OwningAccounts|SubnetIds|ConfigurationTemplates|Versions|kafkaVersions|NameServers|AllowedOrigins|AllowedMethods|AllowedHeaders|ExposeHeaders|Events|InvalidParameters)\\\$$" src/awsquery/default_filters.yaml || echo "OK: no anchored variants remain"
```
Exit 0 + "OK" line printed = success.
  </verify>
  <done>14 specific lines changed; no other edits; grep returns no anchored variants for those exact field names.</done>
</task>

<task type="auto" id="2">
  <title>Delete `ssm.get_parameters Parameters$` entry</title>
  <files>src/awsquery/default_filters.yaml</files>
  <action>
Delete the single line `    - Parameters$` inside the `ssm.get_parameters.columns` block. Keep the surrounding entries (`ARN$`, `Name$`, `DataType$`, `Type$`, `InvalidParameters`, `LastModifiedDate$`, `Selector$`) untouched.

Rationale (from ISSUE.md): `Parameters` (no `$`) would contains-match every flattened `Parameters.<N>.<Field>` column, which is effectively no filter. Deletion is cleaner than a degenerate filter.
  </action>
  <verify>
```bash
cd /workspace/.worktrees/e1bzl-fix-remaining-15-broken-suffix-entries-surfaced-by-audit
awk '/^  get_parameters:/{flag=1} /^  [a-z_]+:$/&&!/^  get_parameters:/{flag=0} flag' src/awsquery/default_filters.yaml | grep -c "Parameters" || true
```
Expected output: 1 (only `InvalidParameters` remains; the bare `Parameters$` line is gone). If output is 2, the delete didn't happen.
  </verify>
  <done>Exactly one line removed inside `ssm.get_parameters.columns`; surrounding lines unchanged.</done>
</task>

<task type="auto" id="3">
  <title>Run audit + tests, confirm zero broken in the fixed set</title>
  <files>(verification only)</files>
  <action>
Run the audit script and the gate test. Confirm:
- audit script exits 0
- the 15 entries fixed in tasks 1 and 2 no longer appear in the broken list
- `make test` is green (no regressions)
- `make lint`, `make format-check`, `make type-check` clean
  </action>
  <verify>
```bash
cd /workspace/.worktrees/e1bzl-fix-remaining-15-broken-suffix-entries-surfaced-by-audit
python3 scripts/audit_default_filters.py 2>&1 | grep -E "^Broken: |BROKEN" | head -20
# Expected: 'Broken: 0' OR 'Broken: N' but with NONE of the 15 service/field pairs from the table above

make test    # all 1346+ tests pass (no new fails)
make lint format-check type-check
```
  </verify>
  <done>Audit shows the 15 service/field pairs are gone from the BROKEN list; all CI gates green.</done>
</task>

</tasks>

<success_criteria>
- [x] All 14 list-of-primitive entries: `$` stripped.
- [x] `ssm.get_parameters Parameters$` entry deleted.
- [x] Audit script reports `Broken: 0` for the fixed set.
- [x] `make test`, `make lint`, `make format-check`, `make type-check` all clean.
- [x] No other files touched.
</success_criteria>

<commit_format>
Plain single-line summaries, ≤72 chars, no body, NO Claude attribution trailer. One atomic commit per task (3 commits total). Per user standing memory (`feedback_no_claude_attribution.md`) — overrides any CLAUDE.md trailer example.
</commit_format>
