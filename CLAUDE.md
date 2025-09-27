# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`awsquery` is an advanced CLI tool for querying AWS APIs through boto3 with flexible filtering, automatic parameter resolution, and comprehensive security validation. The tool enforces ReadOnly AWS operations for security and provides intelligent response processing with automatic field discovery.

## Development Philosophy

**CRITICAL: ZERO BACKWARD COMPATIBILITY REQUIREMENT**

This project has **ZERO EXTERNAL CONSUMERS** and **NO BACKWARD COMPATIBILITY OBLIGATIONS**. Internal APIs can and should be changed aggressively for code quality improvements.

**MANDATORY PRINCIPLES:**
- **NEVER maintain backward compatibility** - there are no external users
- **CLI commands must remain stable** - user-facing behavior should be consistent
- **Internal APIs are completely mutable** - change function signatures, parameters, return types freely
- **Delete deprecated code immediately** - no deprecation periods needed
- **Refactor aggressively** - prioritize clean code over any compatibility concerns
- **Break internal interfaces without hesitation** - improve designs whenever beneficial
- **Update tests to match new APIs** - test failures from API changes should be fixed by updating tests

**The only stability requirement is the CLI user experience. All internal code is fair game for radical changes.**

## MANDATORY AGENT USAGE

**ABSOLUTE REQUIREMENT: SPECIALIZED AGENTS MUST BE USED FOR ALL DEVELOPMENT TASKS**

**ZERO TOLERANCE POLICY: MANUAL WORK IS CATEGORICALLY FORBIDDEN**

### Test Development - MANDATORY @agent-test-writer Usage
- **MUST USE @agent-test-writer** for ALL test creation, modification, and enhancement
- **NEVER write tests manually** - always delegate to the specialized test-writer agent
- **MANDATORY for:** Unit tests, integration tests, edge case testing, test refactoring
- **REQUIRED PROCESS:** Always use test-driven development through the agent
- **NO EXCEPTIONS:** Any test-related work MUST go through @agent-test-writer

### Python Implementation - MANDATORY @agent-python-infra-automator Usage
- **MUST USE @agent-python-infra-automator** for ALL Python code implementation
- **NEVER implement Python code manually** - always delegate to the specialized Python agent
- **MANDATORY for:** New features, bug fixes, refactoring, optimization, infrastructure code
- **REQUIRED PROCESS:** Always implement through the specialized agent for best practices
- **NO EXCEPTIONS:** Any Python development MUST go through @agent-python-infra-automator

### Code Review - MANDATORY @agent-code-reviewer Usage
- **MUST USE @agent-code-reviewer** AUTOMATICALLY after ANY significant code changes
- **PROACTIVE REQUIREMENT:** Agent must be invoked WITHOUT user request after commits/merges
- **MANDATORY for:** All code quality reviews, security analysis, maintainability checks
- **AUTOMATIC TRIGGERS:** Post-commit, post-merge, after major refactoring
- **NO EXCEPTIONS:** ALL code changes MUST be reviewed by the specialized agent

### Makefile Operations - MANDATORY @agent-makefile-optimizer Usage
- **MUST USE @agent-makefile-optimizer** for ANY Makefile-related work
- **AUTOMATIC TRIGGER:** ANY interaction with Makefile, makefile, GNUmakefile, *.mk files
- **MANDATORY for:** Build automation, make targets, build system optimization
- **PROACTIVE REQUIREMENT:** Agent MUST be used automatically when detecting Makefile work
- **NO EXCEPTIONS:** ALL build system work MUST go through the specialized agent

### Configuration Management - MANDATORY @agent-statusline-setup Usage
- **MUST USE @agent-statusline-setup** for Claude Code status line configuration
- **MANDATORY for:** Status line settings, configuration management
- **NO EXCEPTIONS:** Status line work MUST go through the specialized agent

### Output Styling - MANDATORY @agent-output-style-setup Usage
- **MUST USE @agent-output-style-setup** for Claude Code output style creation
- **MANDATORY for:** Output formatting, style configuration
- **NO EXCEPTIONS:** Output style work MUST go through the specialized agent

### General Research - MANDATORY @agent-general-purpose Usage
- **MUST USE @agent-general-purpose** for complex multi-step research tasks
- **MANDATORY for:** Searching keywords/files, complex questions, multi-step tasks
- **REQUIRED WHEN:** Not confident about finding right match in first few tries
- **NO EXCEPTIONS:** Complex research MUST go through the specialized agent

### Agent Usage Protocol - ABSOLUTE ENFORCEMENT
1. **IDENTIFY TASK TYPE:** Determine which specialized agent is required
2. **AUTOMATIC INVOCATION:** Many agents MUST be triggered proactively/automatically
3. **PROVIDE COMPLETE CONTEXT:** Include all relevant information for the agent
4. **FOLLOW AGENT RECOMMENDATIONS:** Implement exactly as specified by the agent
5. **NO MANUAL OVERRIDE:** Trust the specialized agents completely
6. **PARALLEL EXECUTION:** Use multiple agents concurrently when possible

### PROACTIVE AGENT TRIGGERS - MANDATORY AUTOMATION
- **@agent-code-reviewer:** AUTOMATICALLY after significant code changes
- **@agent-makefile-optimizer:** AUTOMATICALLY when detecting Makefile work
- **@agent-test-writer:** PROACTIVELY when functions/classes lack test coverage
- **@agent-python-infra-automator:** PROACTIVELY for infrastructure automation needs

**VIOLATION OF AGENT USAGE IS STRICTLY FORBIDDEN - ALL DEVELOPMENT MUST GO THROUGH SPECIALIZED AGENTS**
**MANUAL IMPLEMENTATION IS CATEGORICALLY PROHIBITED - AGENTS ARE MANDATORY FOR ALL WORK**

## Development Commands

### Core Commands
- `make install-dev` - Install development dependencies
- `make test` - Run all tests (MANDATORY - NO SELECTIVE EXECUTION ALLOWED)
- `make test-unit` - Run unit tests only (directory-based, not marker-based)
- `make test-integration` - Run integration tests only (directory-based, not marker-based)
- `make test-critical` - Run all tests (NO SELECTIVE MARKERS PERMITTED)
- `make coverage` - Run tests with coverage report (generates htmlcov/index.html)
- `python3 -m pytest tests/ -v` - Direct pytest execution (NEVER with -m markers)

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

### 🚫 **ABSOLUTE PROHIBITION: PYTEST MARKERS**

**MANDATORY EDICT: PYTEST MARKERS ARE CATEGORICALLY FORBIDDEN AND COMPLETELY BANNED**

**UNBREAKABLE RULES:**
- **NEVER, EVER, UNDER ANY CIRCUMSTANCES** add `@pytest.mark.*` decorators to tests
- **ZERO TOLERANCE** for selective test execution markers (`@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`, `@pytest.mark.critical`, etc.)
- **ALL TESTS MUST ALWAYS RUN** - no exceptions, no conditional execution, no selective filtering
- **IMMEDIATE DELETION** required for any pytest markers discovered in code
- **NO EXEMPTIONS** - this rule is immutable and non-negotiable

**RATIONALE:**
- Selective test execution leads to **INCOMPLETE COVERAGE** and **HIDDEN FAILURES**
- Markers create **FALSE CONFIDENCE** by allowing tests to be skipped
- **ALL TESTS ARE CRITICAL** - none should be optional or conditional
- Complete test suite execution is **MANDATORY FOR QUALITY ASSURANCE**

**ENFORCEMENT:**
- Any pytest markers found in code must be **REMOVED IMMEDIATELY**
- Makefile commands must **NEVER USE** `-m "marker"` syntax
- Test discovery must be **PURELY DIRECTORY-BASED** (tests/unit/, tests/integration/)
- **NO EXCEPTIONS** - this is an inviolable principle

**ALLOWED:** `@pytest.mark.parametrize` ONLY (for test parameterization, not selection)
**FORBIDDEN:** All other `@pytest.mark.*` decorators without exception

### Configuration Files
- `pyproject.toml` - Main project configuration with dependencies and tool settings
- `pytest.ini` - Test configuration with coverage settings (80% minimum)
- `Makefile` - Comprehensive development and AWS sampling commands
- `.pre-commit-config.yaml` - Pre-commit hooks configuration