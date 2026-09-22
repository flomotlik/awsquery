# AGENTS.md

Conventions for agents working **on this repository**. If you are an agent *using* awsquery to query
AWS, you want `awsquery --docs` instead (source: `src/awsquery/agent-reference.md`).

## Setup and commands

```bash
uv sync --extra dev          # create .venv with dev dependencies (or: make uv-sync)
uv run pytest tests/ -q      # full suite, ~1700 tests, under a minute (or: make uv-test)
make format                  # black + isort, line length 100
make lint                    # flake8 + pylint
make type-check              # mypy
make ci                      # everything CI runs
```

`make install-dev` / `make test` are the pip equivalents and work the same.

Run a single test with `uv run pytest tests/unit/test_x.py::TestClass::test_method -v`.

## Layout

- `src/awsquery/cli.py` — argument parsing, filter-group splitting, the `main()` flow
- `src/awsquery/core.py` — API execution, multi-level parameter resolution
- `src/awsquery/shapes.py` — botocore service-model introspection (credential-free field discovery)
- `src/awsquery/security.py` — read-only enforcement by operation prefix
- `src/awsquery/filters.py`, `formatters.py` — filtering and output rendering
- `src/awsquery/default_filters.yaml`, `default_actions.yaml` — curated per-service defaults
- `src/awsquery/agent-reference.md` — the agent/LLM reference printed by `--docs`

## Non-negotiables

- **The CLI is the only stable contract.** Never change the behaviour or output of an existing flag.
  Internal APIs have no consumers: change signatures, return types and module boundaries freely, and
  delete dead code rather than deprecating it.
- **No pytest markers.** `@pytest.mark.parametrize` is the sole exception; every other
  `@pytest.mark.*` is banned and the whole suite always runs. Test selection is directory-based
  (`tests/unit/`, `tests/integration/`).
- **Test real code.** Mock only external boundaries (boto3, filesystem, network). A test that mocks
  the function it claims to cover, or that only asserts `mock.assert_called()`, does not count.
- **No filler test docstrings.** No restating the test name, no TDD placeholders, no narration.
  Comment only genuinely non-obvious cases.
- **Check for an existing test file before creating one.** Flags belong in `test_cli_flags.py`,
  parser behaviour in `test_cli_parser.py`, filters in `test_filter_implementation.py`.
- **Coverage floor is 80%** (`pytest.ini`).

## Documentation sync

`src/awsquery/agent-reference.md` is the single source of truth for the agent-facing reference. After
editing it, regenerate the mirror and keep the two byte-identical:

```bash
make llms      # copies it to llms-full.txt
```

A test asserts they match, and that every flag the reference documents exists in the parser. Update
the reference in the same commit as any CLI change.

## Commits

Single-line summary, imperative mood, 72 characters maximum, no body. Group related changes into one
commit; keep unrelated changes apart.
