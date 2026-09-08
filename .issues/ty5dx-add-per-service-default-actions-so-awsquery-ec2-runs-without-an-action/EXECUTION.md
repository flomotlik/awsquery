# Execution: Add per-service default actions so `awsquery ec2` runs without an action

**Started:** 2026-09-08T13:11:12Z
**Status:** complete
**Branch:** ty5dx-add-per-service-default-actions-so-awsquery-ec2-runs-without-an-action

## Baseline

`python3 -m pytest tests/ -q` before any changes: 1346 passed.

## Execution Log

- [x] Task 1: Add the curated default_actions.yaml and register it for packaging — commit 1366550
- [x] Task 2: Add load_default_actions() and get_default_action() to config.py — commit 71056cf
- [x] Task 3: Pre-parse argv injection in cli.py plus the no-default stderr fallback — commit e440aea
  - Deviation: [Rule 1 - Bug] `test_argparse_system_exit_handling` in
    tests/integration/test_end_to_end.py asserted the old dead-end behavior (unrecognized
    `--unknown-option value` argv left `args.service='value'`, `args.action=None`, and the old
    combined branch printed the service list and exited 0). The new split branch correctly
    treats a service with no action as "no default configured", prints that service's actions
    on stderr, and exits 1 for the now-nonsensical positional `value`. Changed the test's argv
    to `["awsquery", "--unknown-option"]` (no stray positional) so it still exercises the
    SystemExit(0)-with-unrecognized-flag path it was written for, without asserting on the
    accidental "value"-as-service artifact. Included in commit e440aea.
- [x] Task 4: Curated-map validation, injector, flag pass-through and casing tests — commit 8055ead
  - Deviation: [Rule 1 - Bug] `_inject_default_action`'s `debug_print("Using default action...")`
    was silently swallowed on every real invocation: it runs during the *first*
    `parser.parse_known_args()` call, before `utils.set_debug_enabled(args.debug)` is reached
    later in `main()`, so the global debug flag was still `False` at the moment the injector's
    debug_print executed — the line could never appear on stderr for `awsquery -d ec2`,
    contradicting Task 4's own required test ("`-d ec2` emits the `Using default action` line
    on stderr") and the plan's success criterion that a debug_print announces the chosen
    default. Fixed by pre-enabling debug mode from a lightweight scan of raw `sys.argv[1:]`
    for `-d`/`--debug` immediately before the injection call; the later
    `utils.set_debug_enabled(args.debug)` (now with its redundant `from . import utils`
    removed) still re-applies the authoritative parsed value. Included in commit 8055ead.
- [x] Task 5: Rewrite the vacuously-green integration test at test_end_to_end.py:889 — commit ff45e3b
- [x] Task 6: Document the default-action shortcut in the README — commit 848bb9c

## Verification Results

**`make test`:** 1420 passed (baseline before this issue: 1346 passed; net +74 new/rewritten
tests across the six tasks). Full output tail:
```
============================ 1420 passed in 11.76s =============================
```

**`make lint`:** clean.
```
flake8 src/ tests/ --count --statistics --show-source
0
pylint src/awsquery
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)
```

**`make format-check`:** clean.
```
black --check --diff src/ tests/
All done! (62 files would be left unchanged)
isort --check-only --diff src/ tests/
(no output — clean)
```

**Coverage gate:** `pytest.ini`/`Makefile` do not actually pass `--cov-fail-under` to `make
test` (coverage is opt-in via `make coverage`); nothing to fail on. `make test` completed with
0 non-coverage failures either way.

**Packaging spot-check** (plan-mandated, not coverable by unit tests):
```
python3 -m build
unzip -l dist/*.whl | grep default_actions.yaml
     1604  ...  awsquery/default_actions.yaml
```
Confirms `default_actions.yaml` ships inside the built wheel. `dist/`, `build/`, and
`src/awsquery.egg-info/` were removed after the check (build artifacts, not part of the repo).

**Manual injector spot-check** (matches README examples):
```
_inject_default_action(['ec2']) == ['ec2', 'describe-instances']
_inject_default_action(['s3', '--', 'Name']) == ['s3', 'list-buckets', '--', 'Name']
```

## Deviations from Plan

### Auto-fixed (Rules 1-3)

1. **[Rule 1 - Bug] `test_argparse_system_exit_handling` asserted the old dead-end branch
   behavior** (Task 3, commit e440aea)
   - Found during: Task 3 full-suite verification (`python3 -m pytest tests/ -q`)
   - Issue: `sys.argv = ["awsquery", "--unknown-option", "value"]` left argparse assigning
     `args.service = "value"` (positional match) and `args.action = None`. Before this issue,
     the combined `if not args.service or not args.action:` branch printed the service list and
     exited 0 for this case — the test asserted `exit code == 0`. After splitting the branch
     (per Task 3's own spec), a service with no action but no configured default now correctly
     prints that service's actions on stderr and exits 1, so `"value"` (not a real service)
     produced `ERROR: Unknown service 'value'` and exit 1, failing the old assertion.
   - Fix: Changed the test's argv to `["awsquery", "--unknown-option"]` (no stray positional),
     which still leaves `args.service = None` and exercises the same "unrecognized flag doesn't
     crash the parser, still exits 0" intent the test was written for, without depending on the
     accidental "value"-as-service artifact that the new behavior correctly stops tolerating.
   - Files: `tests/integration/test_end_to_end.py`

2. **[Rule 1 - Bug] `_inject_default_action`'s debug_print was silently swallowed on every real
   invocation** (Task 4, commit 8055ead)
   - Found during: Task 4, writing the required test that `-d ec2` emits the `Using default
     action` line on stderr
   - Issue: the injector's `debug_print(...)` executes during the *first*
     `parser.parse_known_args()` call, which is chronologically before
     `utils.set_debug_enabled(args.debug)` runs later in `main()`. The global debug flag was
     therefore still `False` at the moment the injector's debug_print fired, so the line could
     never appear on stderr for `awsquery -d ec2` — contradicting both Task 4's required test
     and the plan's stated success criterion ("Only a debug_print announces the chosen
     default").
   - Fix: pre-enable debug mode from a lightweight scan of raw `sys.argv[1:]` for `-d`/`--debug`
     immediately before the injection call; the later `utils.set_debug_enabled(args.debug)`
     (with its now-redundant `from . import utils` removed) still re-applies the authoritative
     parsed value, so final debug state is unaffected — only the injector's own debug line was
     previously lost.
   - Files: `src/awsquery/cli.py`

### Blocked (Rule 4)

None.

## Discovered Issues

None found outside the scope of this issue.

## Self-Check

- [x] All files from plan exist (verified: `src/awsquery/default_actions.yaml`,
  `src/awsquery/config.py`, `src/awsquery/cli.py`, `pyproject.toml`, all five test files,
  `README.md`)
- [x] All 6 commit hashes exist on branch (`git log --oneline` confirmed:
  1366550, 71056cf, e440aea, 8055ead, ff45e3b, 848bb9c)
- [x] Full verification suite passes for real: `make test` (1420 passed), `make lint` (clean),
  `make format-check` (clean), plus the plan's packaging spot-check
- [x] No stubs/TODOs/placeholders introduced (`grep -iE "TODO|FIXME|HACK|XXX|PLACEHOLDER|coming
  soon|not implemented"` over the diff: no matches)
- [x] No leftover debug code (`grep` over the diff for `console.log`/`debugger`/`binding.pry`/
  `breakpoint()` bare prints: no matches; all `print()`/`debug_print()` calls are intentional
  CLI output or the existing debug-logging convention)
- **Result:** PASSED

**Completed:** 2026-09-08T13:21:59Z
**Duration:** ~11 minutes
**Commits:** 6
