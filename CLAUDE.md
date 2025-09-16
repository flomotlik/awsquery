# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`awsquery` is an advanced CLI tool for querying AWS APIs through boto3 with flexible filtering, automatic parameter resolution, and comprehensive security validation. The tool enforces ReadOnly AWS operations for security and provides intelligent response processing with automatic field discovery.

## Development Philosophy

**IMPORTANT: Backward compatibility is NEVER a goal and NEVER needs to be achieved.** This is a self-contained tool with no external dependencies or consumers. Always prioritize:
- Clean, maintainable code over compatibility
- Removing deprecated functions and patterns immediately
- Refactoring without hesitation when improvements are identified
- Simplifying APIs and removing wrapper functions

## Development Commands

### Core Commands
- `make install-dev` - Install development dependencies
- `make test` - Run all tests 
- `make test-unit` - Run unit tests only
- `make test-integration` - Run integration tests only
- `make test-critical` - Run critical path tests
- `make coverage` - Run tests with coverage report (generates htmlcov/index.html)
- `python3 -m pytest tests/ -v` - Direct pytest execution

### Code Quality
- `make lint` - Run linting checks (flake8, pylint)
- `make format` - Format code with black and isort
- `make format-check` - Check code formatting without changes
- `make type-check` - Run mypy type checking
- `make security-check` - Run security checks (bandit, safety)
- `make pre-commit` - Run pre-commit hooks on all files

### Docker Development
- `make docker-build` - Build development container
- `make shell` - Open interactive shell in container
- `make test-in-docker` - Run tests in Docker container

### Single Test Execution
- `python3 -m pytest tests/test_specific.py::TestClass::test_method -v` - Run specific test
- `python3 -m pytest -k "test_pattern" -v` - Run tests matching pattern
- `python3 -m pytest tests/ -m "unit" -v` - Run tests with specific markers

## Architecture

### Core Module Structure
- `src/awsquery/cli.py` - Main CLI interface and argument parsing
- `src/awsquery/core.py` - Core AWS query execution logic
- `src/awsquery/security.py` - Security policy validation (ReadOnly enforcement)
- `src/awsquery/filters.py` - Data filtering and column selection logic
- `src/awsquery/formatters.py` - Output formatting (table/JSON)
- `src/awsquery/utils.py` - Utility functions and debug helpers

### Key Features
- **Smart Multi-Level Calls**: Automatically resolves missing parameters by inferring list operations
- **Security-First Design**: All operations validated against `policy.json` ReadOnly policy
- **Flexible Filtering**: Multi-level filtering with `--` separators for different filter types
- **Auto-Parameter Resolution**: Handles both specific fields and standard AWS patterns (Name, Id, Arn)
- **Intelligent Response Processing**: Clean extraction of list data, ignoring AWS metadata

### Security Architecture
The tool enforces security through a comprehensive `policy.json` file that defines allowed ReadOnly AWS operations. All API calls are validated against this policy before execution.

### Testing Structure
- Unit tests in `tests/unit/` with `@pytest.mark.unit`
- Integration tests in `tests/integration/` with `@pytest.mark.integration`
- Critical path tests marked with `@pytest.mark.critical`
- AWS mocks using moto library marked with `@pytest.mark.aws`

### STRICT Testing Requirements - MUST FOLLOW

#### 🚫 PROHIBITED: Test Anti-Patterns
**NEVER CREATE:**
1. **Duplicate Test Files**: Before creating ANY test file, search for existing tests covering the same functionality
   - Flag tests: Use `test_cli_flags.py` ONLY
   - Parser tests: Use `test_cli_parser.py` ONLY
   - Filter tests: Use `test_filter_implementation.py` for real tests, `test_filter_matching.py` for patterns
2. **Over-Mocked Tests**: Tests that mock the very functions they claim to test
3. **Mock Assertion Tests**: Tests that only verify `mock.assert_called()` without testing actual behavior
4. **Nested Mock Contexts**: More than 2 levels of `with patch()` indicates over-mocking

#### ✅ REQUIRED: Test Best Practices
**ALWAYS:**
1. **Test Real Implementation**:
   ```python
   # GOOD: Tests actual function
   result = filter_resources(real_data, ["filter"])
   assert len(result) == expected

   # BAD: Only tests mock
   mock_filter.return_value = []
   mock_filter.assert_called_once()
   ```

2. **Minimal Mocking**: Only mock external dependencies (boto3, file I/O, network)
   ```python
   # GOOD: Only mock AWS
   @patch("boto3.client")
   def test_feature(mock_client):
       # Test real code with mocked AWS

   # BAD: Mock everything
   @patch("filter_resources")
   @patch("format_output")
   @patch("parse_args")
   ```

3. **Consolidate Related Tests**: Group similar tests in one file
   - All flag position tests → `test_cli_flags.py`
   - All parser tests → `test_cli_parser.py`
   - All filter implementation → `test_filter_implementation.py`

4. **Test Edge Cases**: Include malformed input, Unicode, empty values
   ```python
   # Test edge cases
   test_cases = ["", None, "^$", "ˆ", "$^", "^^$$"]
   ```

5. **Verify Actual Output**: Check real results, not mock calls
   ```python
   # GOOD: Verify actual JSON
   output = format_json_output(data, filters)
   parsed = json.loads(output)  # Ensures valid JSON

   # BAD: Only check mock called
   mock_json.assert_called_once()
   ```

#### 📋 Test Review Checklist
Before committing ANY test:
1. ❓ Does a test file for this feature already exist?
2. ❓ Am I testing real code or just mocks?
3. ❓ Do assertions verify actual behavior?
4. ❓ Is mocking limited to external dependencies only?
5. ❓ Are edge cases covered?

#### 🔍 Finding Duplicate Tests
```bash
# Check for existing tests before creating new ones
grep -r "test.*flag.*position" tests/
grep -r "test.*parser" tests/
grep -r "test.*filter" tests/
```

### Test Documentation Requirements
- **Minimal Comments**: Remove all unnecessary verbose comments from test files
- **Essential Only**: Keep comments only for complex test logic, specific assertions, or edge cases
- **No Redundant Docstrings**: Avoid docstrings that simply restate method names
- **Purpose Over Process**: Document WHY tests exist, not HOW they work (unless complex)
- **Clean Signal-to-Noise**: Prioritize readable code over explanatory comments

### Configuration Files
- `pyproject.toml` - Main project configuration with dependencies and tool settings
- `pytest.ini` - Test configuration with coverage settings (80% minimum)
- `Makefile` - Comprehensive development and AWS sampling commands
- `.pre-commit-config.yaml` - Pre-commit hooks configuration