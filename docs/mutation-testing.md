# Mutation Testing with Mutmut

This project uses `mutmut` for mutation testing to verify test suite quality.

## Installation

Mutmut is included in development dependencies:

```bash
pip install -e ".[dev]"
```

## Configuration

Mutation testing is configured in `pyproject.toml`:

```toml
[tool.mutmut]
paths_to_mutate = ["src/awsquery/"]
runner = "python -m pytest -x -q"
```

## Usage

### Run Mutation Testing

```bash
# Run complete mutation testing
make mutmut

# Or directly
mutmut run
```

### View Results

```bash
# Show summary of results
make mutmut-results

# Generate HTML report
make mutmut-html

# Clean mutation cache
make mutmut-clean
```

## Interpreting Results

Mutmut creates mutations in your code and runs tests to see if they detect the changes:

- **Killed**: Test suite detected the mutation (good)
- **Survived**: Test suite didn't detect the mutation (indicates missing test coverage)
- **Timeout**: Mutation caused infinite loop or significant slowdown
- **Suspicious**: Test behavior inconsistent

## Best Practices

1. Focus on critical code paths first
2. Run on specific modules during development
3. Use mutation testing to identify weak test areas
4. Not all survived mutations need fixing - use judgment

## Example: Testing Specific Module

```bash
# Test only the filters module
mutmut run src/awsquery/filters.py
```

## Performance Tips

- Use `--max-children` to limit parallel processes
- Run on subsets of code during development
- Full runs can be done in CI or before releases