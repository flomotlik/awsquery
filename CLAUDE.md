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