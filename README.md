# awsquery - AWS API Query Tool

AWS CLI tool to run any awscli read command and filter the resulting Values and JSON for custom table output.

The following command will find all ec2 instances where `prod`and `web` are found somewhere in the Value
of any key of the whole response. For all matching resources it will extract all fields that match
any of the second filters, so anything that matches `Tags.Name`, `State`, `InstanceId` or `vpcid`.
```
awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId vpcid
```

This creates endless flexibility to shape your aws cli calls, filter any output and present exactly
the data you need during review, debugging or development.

## Quick Start

With [uv](https://docs.astral.sh/uv/) installed, there is nothing else to set up — no virtualenv, no
`pip install`, not even a Python of your own:

```bash
uvx awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId
```

Want it as a permanent command with tab completion?

```bash
uv tool install awsquery
awsquery ec2 describe-instances
```

See [Installation](#installation) for aliases, version pinning, running straight from GitHub, and CI
usage.

## Features

- **Smart Multi-Level Calls**: Automatically resolves missing parameters by inferring and calling list operations
- **Flexible Filtering**: Multi-level filtering with `--` separators for resource, value, and column filters
- **Partial Matching**: All filters use case-insensitive partial matching (both value and column filters)
- **Keys Discovery**: Show all available fields from any API response with `-k`/`--keys` (fixed to show keys from successful responses)
- **Debug Mode**: Comprehensive debug output with `-d`/`--debug` featuring structured output with timestamps and DebugContext tracking
- **Security Validation**: Enforces ReadOnly AWS operations with comprehensive validation
- **Smart Auto-completion**: Enhanced tab completion with split matching and prefix priority for AWS services and actions
- **Smart Parameter Extraction**: Handles both specific fields and standard AWS field patterns (Name, Id, Arn)
- **Intelligent Response Processing**: Clean extraction of list data, ignoring metadata
- **Tabular Output**: Customizable column display with automatic filtering
- **Pagination Support**: Handles large AWS responses automatically
- **Region/Profile Support**: AWS CLI-compatible `--region` and `--profile` arguments for session management
- **Tag Transformation**: Automatic conversion of AWS Tags list to key-value pairs for better readability
- **Default Column Filters**: Configuration-based default columns for common AWS queries
- **Default Actions**: A bare service name runs its curated default operation — `awsquery ec2`
  == `awsquery ec2 describe-instances` (e.g. `awsquery s3 -- Name`)
- **Parameter Passing**: Direct parameter passing to AWS APIs with `-p`/`--parameter` for advanced use cases
- **Hint-Based Resolution**: Function selection hints with `-i`/`--input` for multi-step calls, including cross-service support and field extraction targeting

## Installation

`awsquery` is on PyPI, so the fastest way to use it is [uv](https://docs.astral.sh/uv/): no
virtualenv, no `pip install`, no Python version juggling. uv downloads a matching Python for you if
you don't have one.

| You want to... | Command |
| --- | --- |
| Try it once, install nothing | `uvx awsquery ec2 describe-instances` |
| Use it every day (and get tab completion) | `uv tool install awsquery` |
| Run a specific version | `uvx awsquery@1.1.0 ec2 describe-instances` |
| Run unreleased code from GitHub | `uvx --from git+https://github.com/flomotlik/awsquery awsquery ec2` |
| Hack on it locally | `uv run awsquery ec2` inside a checkout |

### Install uv (one time)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Homebrew
brew install uv

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

That is the only thing anyone on your team has to install. uv itself is a single binary and brings
its own Python.

### Run without installing: `uvx`

```bash
uvx awsquery ec2 describe-instances
uvx awsquery s3 list-buckets backup -- Name CreationDate
uvx awsquery -j cloudformation describe-stacks prod
```

The first run downloads awsquery and its dependencies into uv's cache (a few seconds). Every run
after that starts in about a tenth of a second. Nothing is added to your `PATH`, no virtualenv is
created, and nothing is left behind in your project.

Pin an exact version when you want reproducibility, or force a check for the newest release:

```bash
uvx awsquery@1.1.0 ec2 describe-instances   # pinned, fully reproducible
uvx awsquery@latest ec2 describe-instances  # re-checks PyPI for a newer version
```

### Make it feel like a normal command: alias

Add one line to your shell config and the whole team is running the same tool without installing
anything:

```bash
# ~/.bashrc or ~/.zshrc
alias awsquery='uvx awsquery@latest'

# pin the version instead, if you want everyone on the same release
alias awsquery='uvx awsquery@1.1.0'
```

```fish
# ~/.config/fish/config.fish
alias --save awsquery 'uvx awsquery@latest'
```

```powershell
# PowerShell $PROFILE
function awsquery { uvx awsquery@latest @args }
```

Then use it exactly as documented everywhere else in this README:

```bash
awsquery ec2 describe-instances prod web -- Tags.Name State InstanceId
```

Two things to know about the alias route: `@latest` contacts PyPI on every invocation (so it needs
network and adds a moment of latency), and shell tab completion does not work through an alias
because argcomplete needs a real executable on `PATH`. If either matters to you, use
`uv tool install` instead — it gives you the same command with neither drawback.

### Install as a persistent tool: `uv tool install`

```bash
uv tool install awsquery      # installs the awsquery command into ~/.local/bin
awsquery ec2 describe-instances

uv tool upgrade awsquery      # upgrade later
uv tool uninstall awsquery    # remove it again
uv tool list                  # see what's installed
```

uv keeps awsquery in its own isolated environment, so it can never conflict with your project
virtualenvs or your system Python. If the command isn't found afterwards, run `uv tool update-shell`
(it adds uv's bin directory to your `PATH`) and restart your shell.

This is the recommended setup for daily use and the one that supports
[shell autocomplete](#enable-shell-autocomplete).

### Run unreleased code straight from GitHub

```bash
# latest commit on main, run once
uvx --from git+https://github.com/flomotlik/awsquery awsquery ec2 describe-instances

# a specific branch, tag or commit
uvx --from git+https://github.com/flomotlik/awsquery@main awsquery ec2 describe-instances
uvx --from git+https://github.com/flomotlik/awsquery@v1.1.0 awsquery ec2 describe-instances

# install that version persistently
uv tool install git+https://github.com/flomotlik/awsquery
```

`--from` is needed because the package name (`awsquery`) has to be resolved from the repository
while the command to execute is still `awsquery`.

### Run from a local checkout

```bash
git clone https://github.com/flomotlik/awsquery.git
cd awsquery

# run the working tree directly - uv creates and syncs .venv on the fly
uv run awsquery ec2 describe-instances

# or via make
make uv-run ARGS="ec2 describe-instances"

# put your local checkout on PATH as the global awsquery command
uv tool install --editable .   # same as: make tool-install
```

`uv run` resolves dependencies from `uv.lock`, which is committed to this repository, so every
contributor gets an identical environment. Use `uv run --frozen awsquery ...` to fail instead of
silently re-locking if the lockfile is out of date.

### Python versions

awsquery requires Python 3.10 or newer. uv fetches a suitable interpreter automatically, so you do
not need a system Python at all. To force a specific version:

```bash
uvx --python 3.12 awsquery ec2 describe-instances
uv tool install --python 3.12 awsquery
uv run --python 3.12 awsquery ec2 describe-instances
```

### AWS credentials with uv

uvx does not sandbox anything: the tool runs as you, with your environment and your `~/.aws`
directory, so credentials, SSO sessions, profiles, assumed roles and `AWS_*` environment variables
all behave exactly as they do with the AWS CLI.

```bash
AWS_PROFILE=prod uvx awsquery ec2 describe-instances
uvx awsquery --profile prod --region eu-central-1 ec2 describe-instances
```

### Using awsquery in CI

No install step is needed beyond uv itself:

```yaml
# GitHub Actions
- uses: astral-sh/setup-uv@v6
- run: uvx awsquery@1.1.0 -j cloudformation describe-stacks -- StackName StackStatus
  env:
    AWS_REGION: eu-central-1
```

Pin the version (`awsquery@1.1.0`) in CI so a new release can never change your output format
underneath a pipeline.

### Via pip

If your team does not use uv, the classic routes still work:

```bash
pip install awsquery       # into the current environment
pipx install awsquery      # isolated, like uv tool install
```

### Development installation

```bash
git clone https://github.com/flomotlik/awsquery.git
cd awsquery
uv sync --extra dev        # or: make uv-sync
uv run pytest tests/ -v    # or: make uv-test
```

The pip equivalent is `pip install -e ".[dev]"` (`make install-dev`).

### Enable Shell Autocomplete

awsquery supports tab completion for AWS services and actions through argcomplete.

Completion requires a real `awsquery` executable on your `PATH`, because the shell calls that
executable to compute the candidates. So it works with `uv tool install awsquery`, `pipx install`
and `pip install` — but **not** with a `uvx` alias, since the alias is expanded by your shell after
completion has already run.

```bash
uv tool install awsquery   # the setup below assumes this (or pip/pipx)
```

#### Setup

The `register-python-argcomplete` helper comes from argcomplete. With uv you never have to install
it: `uvx --from argcomplete register-python-argcomplete` runs it on demand.

##### Bash
```bash
# Add to ~/.bashrc or ~/.bash_profile
eval "$(uvx --from argcomplete register-python-argcomplete awsquery)"

# If argcomplete is already installed in your environment (pip/pipx users):
eval "$(register-python-argcomplete awsquery)"
```

##### Zsh
```bash
# Add to ~/.zshrc
autoload -U bashcompinit && bashcompinit
eval "$(uvx --from argcomplete register-python-argcomplete awsquery)"
```

##### Fish
```bash
# Add to ~/.config/fish/config.fish
uvx --from argcomplete register-python-argcomplete --shell fish awsquery | source
```

To keep shell startup instant, write the completion script to a file once and source that instead of
calling uvx on every new shell:

```bash
uvx --from argcomplete register-python-argcomplete awsquery > ~/.awsquery-complete.sh
echo 'source ~/.awsquery-complete.sh' >> ~/.zshrc   # or ~/.bashrc
```

After adding the appropriate line to your shell configuration, restart your shell or source the file:
```bash
source ~/.bashrc  # or ~/.zshrc, etc.
```

Now you can use enhanced tab completion with smart matching:
```bash
awsquery <TAB>              # Shows available services
awsquery ec2 <TAB>          # Shows available ec2 actions
awsquery s3 list-<TAB>      # Shows s3 list actions
awsquery ec2 desc-inst<TAB> # Smart completion: "desc-inst" matches "describe-instances"
awsquery cloudformation des-sta<TAB> # Matches "describe-stacks"
```

The autocomplete system now features:
- **Split matching**: "desc-inst" matches "describe-instances"
- **Prefix priority**: Exact prefix matches are prioritized over substring matches
- **Security filtering**: Only shows ReadOnly operations

## Usage

### Basic Query
```bash
# Query EC2 instances with filtering
awsquery ec2 describe-instances

# Filter by values (partial match, case-insensitive on ANY field)
awsquery ec2 describe-instances prod web

# Specify output columns (partial match, case-insensitive)
awsquery ec2 describe-instances prod -- Name State InstanceId

# List S3 buckets containing "backup" (matches if "backup" appears anywhere in any field)
awsquery s3 list-buckets backup

# JSON output format
awsquery -j s3 list-buckets
```

### Keys Discovery
```bash
# Show available fields/keys from an API response
awsquery -k ec2 describe-instances
awsquery --keys s3 list-buckets
```

### Discovery and Debug
```bash
# List available services
awsquery

# Debug mode for troubleshooting with enhanced DebugContext output
# Shows structured debug information with timestamps and execution flow
awsquery -d ec2 describe-instances
```

## Command Structure

```
awsquery [-j|--json] [--format FMT] [--limit N] [-k|--keys] [-d|--debug] [-p PARAM] [-i HINT] [--region REGION] [--profile PROFILE] SERVICE ACTION [VALUE_FILTERS...] [-- TABLE_OUTPUT_FILTERS...]
```

- **SERVICE**: AWS service name (ec2, s3, iam, etc.)
- **ACTION**: Service action (describe-instances, list-buckets, etc.)
- **VALUE_FILTERS**: Space-separated filters - ALL must match, using case-insensitive partial matching on any field
- **TABLE_OUTPUT_FILTERS**: Column selection - partial, case-insensitive matching on column names
- **-j, --json**: Output results in JSON format instead of table
- **-k, --keys**: Show all available keys for the command
- **-d, --debug**: Enable debug output for troubleshooting
- **-p, --parameter PARAM**: Pass parameters directly to AWS API (key=value format, propagates to list operations)
- **-i, --input HINT**: Multi-step control with cross-service support and function/field/limit hints (e.g., "ec2:desc-inst:instanceid", "desc-clus", ":arn", "::5")
- **--region REGION**: AWS region to use for requests (e.g., us-west-2)
- **--profile PROFILE**: AWS profile to use from ~/.aws/credentials

## Security

- **ReadOnly Enforcement**: Only AWS ReadOnly operations are permitted
- **Input Sanitization**: Prevents injection attacks through parameter validation
- **Operation Validation**: All actions validated before execution
- **Wildcard Matching**: Supports AWS IAM wildcard patterns (e.g., `ec2:Describe*`)
- **Session Isolation**: Each profile/region maintains separate boto3 sessions
- **Security Testing**: Comprehensive test suite validates security constraints

## Examples

```bash
# Find instances with "prod" AND "web" in any field (partial match)
# e.g., matches "production-web-server", "web.prod.example.com"
awsquery ec2 describe-instances prod web

# Show only columns matching Name, State and InstanceId (partial match)
# e.g., "Name" matches "InstanceName", "Tags.Name", "SecurityGroupName"
awsquery ec2 describe-instances prod web -- Name State InstanceId

# Find S3 buckets with "backup" anywhere in the data
# e.g., matches "my-backup-bucket", "bucket-backup-2024", "backups"
awsquery s3 list-buckets backup

# Multi-level CloudFormation query with parameter resolution
# Filters: "prod" in stack data, columns containing "Created" or "StackName"
awsquery cloudformation describe-stack-events prod -- Created StackName

# Targeted field extraction with hint for multi-step calls
awsquery elbv2 describe-tags -i desc-clus:clusterarn prod

# Discover all available keys
awsquery -k ec2 describe-instances

# JSON output with filtering (partial column name matching)
awsquery -j ec2 describe-instances prod -- InstanceId State.Name

# Debug mode with enhanced output showing parameter resolution and API calls
awsquery -d cloudformation describe-stack-resources workers -- EKS

# Use specific AWS region
awsquery --region eu-west-1 ec2 describe-instances

# Use specific AWS profile
awsquery --profile production s3 list-buckets

# Combine region and profile
awsquery --region us-east-2 --profile dev ec2 describe-vpcs

# View transformed tags (partial match on column names)
# Shows any column containing "Tags.Name" or "Tags.Environment"
awsquery ec2 describe-instances -- Tags.Name Tags.Environment

# CloudTrail LookupEvents with complex parameter structures
# Filter events by event name with automatic type conversion
awsquery cloudtrail lookup-events -p LookupAttributes=AttributeKey=EventName,AttributeValue=ConsoleLogin

# Multiple CloudTrail attributes using semicolon separation
awsquery cloudtrail lookup-events -p LookupAttributes=AttributeKey=EventName,AttributeValue=AssumeRole;AttributeKey=Username,AttributeValue=admin

# CloudTrail with time range and resource type filtering
awsquery cloudtrail lookup-events -p StartTime=2024-01-01 -p EndTime=2024-01-31 -p LookupAttributes=AttributeKey=ResourceType,AttributeValue=AWS::S3::Bucket

### Advanced Parameter Passing

# Pass specific parameters to AWS API calls
awsquery ec2 describe-instances -p MaxResults=10
awsquery ec2 describe-instances -p InstanceIds=i-123,i-456 -p MaxResults=5

# Complex parameter structures for SSM with automatic type conversion
awsquery ssm describe-parameters -p ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu,2024

# Multiple complex structures using semicolon separation
awsquery ssm describe-parameters -p ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu;Key=Type,Option=Equal,Values=String

# Complex structures with nested arrays and type conversion
awsquery ec2 describe-instances -p Filters=Name=instance-state-name,Values=running,stopped;Name=tag:Environment,Values=prod,staging

### Hint-Based Multi-Step Resolution

# Use hints to guide automatic parameter resolution
# When describe-tags needs resource ARNs, hint at using describe-clusters
awsquery elbv2 describe-tags -i desc-clus prod

# CloudFormation stack resources with hint for stack selection
awsquery cloudformation describe-stack-resources -i desc-stacks production

# ECS service details with task definition hint
awsquery ecs describe-services -i desc-task web-service

# Field-specific extraction with function:field format
awsquery elbv2 describe-tags -i desc-clus:clusterarn prod  # Extract ClusterArn specifically
awsquery eks describe-fargate-profile -i desc-clus:rolearn  # Extract RoleArn instead of default

# Limit results from multi-step calls (default is 10)
awsquery ssm get-parameters -i ::5  # Limit to 5 parameters
awsquery ec2 describe-network-interfaces -i ::20  # Limit to 20 interfaces
awsquery ec2 describe-network-interfaces -i ::0  # Unlimited (remove default limit)

# Field override without function hint (uses inferred function)
awsquery ecs describe-tasks -i :clusterarn  # Extract ClusterArn field
awsquery rds describe-db-clusters -i :endpoint  # Extract Endpoint field

# Combined: field and limit
awsquery elbv2 describe-tags -i :arn:3  # Extract ARN field, limit to 3 resources

# Full syntax: function, field, and limit
awsquery elbv2 describe-tags -i desc-clus:clusterarn:5  # Use desc-clus, extract ClusterArn, limit to 5

### Cross-Service Parameter Resolution

# Use service prefixes to resolve parameters from different AWS services
# Resolve EC2 instance IDs to use with SSM patch state queries
awsquery ssm describe-instance-patch-states -i ec2:describe-instances:instanceid prod

# Service-only hint: Let EC2 service auto-infer the operation
awsquery ssm describe-instance-patch-states -i ec2 prod

# Use S3 bucket names for CloudTrail event lookup
awsquery cloudtrail lookup-events -i s3:list-buckets:name backup

# Get IAM user names for access key queries
awsquery iam list-access-keys -i iam:list-users:username:5

# Cross-service with EKS clusters for ECS task definitions
awsquery ecs describe-task-definition -i eks:describe-clusters:name prod-cluster

# Combine cross-service with field extraction and limits
awsquery autoscaling describe-auto-scaling-instances -i ec2:desc-inst:instanceid:10 prod

# Service-only with field hint (operation auto-inferred)
awsquery ssm describe-instance-patch-states -i ec2::instanceid prod
```

## Configuration

### AWS Credentials

Ensure AWS credentials are configured via:
- `~/.aws/credentials` (supports multiple profiles)
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM roles (if running on EC2/ECS/Lambda)
- AWS SSO profiles

### Default Filters Configuration

The tool uses `default_filters.yaml` to define default columns for common queries. This comprehensive configuration file (3000+ lines)
provides extensive pre-configured filters for dozens of AWS services, loaded from the package directory to provide you with standard
columns if you don't add any. Prefix any column filter with `+` to merge with the defaults instead of replacing them — see
[Additive Column Filters (`+Column`)](#additive-column-filters-column) below.

Example configuration:
```yaml
ec2:
  describe_instances:
    columns:
      - InstanceId
      - Tags.Name
      - State.Name
      - InstanceType
      - PrivateIpAddress

s3:
  list_buckets:
    columns:
      - Name
      - CreationDate
```

### Default Actions Configuration

Running `awsquery <service>` with no action runs that service's curated default operation —
`awsquery ec2` is equivalent to `awsquery ec2 describe-instances`. This also works with column
filters after `--`: `awsquery ec2 -- InstanceId` behaves identically to
`awsquery ec2 describe-instances -- InstanceId`.

| Command | Equivalent to |
|---------|---------------|
| `awsquery ec2` | `awsquery ec2 describe-instances` |
| `awsquery s3` | `awsquery s3 list-buckets` |
| `awsquery ec2 -- InstanceId` | `awsquery ec2 describe-instances -- InstanceId` |

The curated map lives in `src/awsquery/default_actions.yaml` as a flat `service: action` map.
**Values must be kebab-case** — the ReadOnly validator only recognizes kebab-case operation
spellings; a snake_case value turns `is_readonly_operation` false, and the command falls
through to an interactive confirmation prompt instead of running.

```yaml
ec2: describe-instances
s3: list-buckets
lambda: list-functions
iam: get-account-summary
```

Adding a service is a one-line YAML edit. Every entry must satisfy two rules: the operation
must be ReadOnly, and it must take no required parameters (so it can run without extra
arguments). A service with no curated entry prints its available ReadOnly actions on stderr
and exits non-zero; `awsquery` with no service at all is unchanged — it still lists available
services on stdout and exits 0.

## Development

### Environment setup with uv

```bash
# Create .venv and install the project plus dev dependencies from uv.lock
uv sync --extra dev          # or: make uv-sync

# Run anything inside that environment without activating it
uv run awsquery ec2 describe-instances   # or: make uv-run ARGS="ec2 describe-instances"
uv run pytest tests/ -v                  # or: make uv-test
uv run black src tests
uv run mypy src

# Update the lockfile after changing dependencies in pyproject.toml
uv lock                      # or: make uv-lock

# Install your working tree as the global awsquery command
uv tool install --editable . # or: make tool-install
uv tool uninstall awsquery   # or: make tool-uninstall
```

`uv.lock` is committed, so `uv sync` gives every contributor byte-identical dependency versions.
Regenerate it with `uv lock` whenever `pyproject.toml` dependencies change and commit the result.

The `make` targets below use pip and the system Python; they work unchanged if you prefer that.

### Running Tests

```bash
# Install development dependencies
make install-dev

# Run all tests
make test

# Run tests with coverage
make coverage

# Run specific test categories
make test-unit
make test-integration
make test-critical  # Run all tests (comprehensive test suite)

# Code formatting and linting
make format
make format-check  # Check without modifying
make lint
make type-check    # Run mypy type checking
make security-check  # Run security analysis

# Mutation testing
make mutmut        # Run mutation tests
make mutmut-results # Show mutation test results
make mutmut-html   # Generate HTML mutation test report

# Pre-commit hooks
make pre-commit  # Run all pre-commit hooks

# Continuous Integration
make ci  # Run comprehensive CI pipeline (tests, linting, type-check, security)
```


### Docker Usage

```bash
# Build development container
make docker-build

# Open interactive shell
make shell

# Run tests in Docker
make test-in-docker

# Clean Docker artifacts
make docker-clean
```

### Development Workflow

```bash
# Watch tests (auto-run on file changes)
make watch-tests

# Build distribution packages
make build

# Clean build artifacts
make clean

# Publish to Test PyPI
make publish-test

# Publish to PyPI (production)
make publish

# Version management
make version  # Show current version
make release  # Create a new release with version bump
```

## Advanced Usage

### Filter Matching Behavior

All filters in awsquery use **case-insensitive matching** with optional anchoring:

#### Filter Operators
- `^` at the start: matches values that START WITH the pattern (prefix match)
  - Both `^` (U+005E) and `ˆ` (U+02C6) are supported for keyboard compatibility
- `$` at the end: matches values that END WITH the pattern (suffix match)
- `^...$`: matches values that EXACTLY equal the pattern (exact match)
- No operators: matches values that CONTAIN the pattern (partial match)

#### Value Filters (before `--`)
- Match against ANY field in the response data
- ALL specified filters must match (AND logic)
- Case-insensitive matching with optional anchoring

```bash
# "prod" matches: "production", "prod-server", "my-prod-app" (contains)
awsquery ec2 describe-instances prod

# "^prod" matches: "production", "prod-server" (starts with)
awsquery ec2 describe-instances ^prod

# "prod$" matches: "my-prod", "dev-prod" (ends with)
awsquery ec2 describe-instances prod$

# "^prod$" matches: only exactly "prod" (exact match)
awsquery ec2 describe-instances ^prod$

# Both filters must match (AND logic)
awsquery ec2 describe-instances ^prod web$
```

#### Column Filters (after `--`)
- Match against column/field names in the output
- Case-insensitive matching with optional anchoring
- Multiple columns can be specified

```bash
# "Instance" matches: "InstanceId", "InstanceType", "InstanceName" (contains)
awsquery ec2 describe-instances -- Instance

# "^Instance" matches: "InstanceId", "InstanceType" (starts with)
awsquery ec2 describe-instances -- ^Instance

# "Name$" matches: "InstanceName", "GroupName", "Tags.Name" (ends with)
awsquery ec2 describe-instances -- Name$

# "^State.Name$" matches: only exactly "State.Name" (exact match)
awsquery ec2 describe-instances -- ^State.Name$

# Multiple patterns
awsquery ec2 describe-instances -- ^Instance Name$ State
```

#### Additive Column Filters (`+Column`)

By default, supplying any column filter REPLACES the curated defaults from `default_filters.yaml`.
Prefix any column with `+` to merge with the defaults instead:

| Command                                                  | Columns shown                                                                                          |
| :------------------------------------------------------- | :----------------------------------------------------------------------------------------------------- |
| `awsquery ec2 describe-instances`                        | `default_filters.yaml` defaults                                                                        |
| `awsquery ec2 describe-instances -- InstanceId`          | only `InstanceId` (replaces defaults)                                                                  |
| `awsquery ec2 describe-instances -- +InstanceId`         | defaults + `InstanceId` (merged, deduped, defaults first)                                              |
| `awsquery ec2 describe-instances -- InstanceId +OwnerId` | defaults + `InstanceId` + `OwnerId` (any `+` triggers additive mode for the whole column-filter group) |
| `awsquery ec2 -- +InstanceId`                            | defaults + `InstanceId`, using the `ec2` default action                                                |

Notes:
- `+` is recognised anywhere in the column-filter group (after the `--` separator).
- Order is defaults first, then your `+`-prefixed and bare columns in CLI order.
- Dedup is case-sensitive on the exact pattern string: `+Foo` plus default `Foo` collapses to one column; `+foo` plus `Foo` keeps both.
- `+` applies only to column filters — value/resource filter behaviour is unchanged.

### Multi-Level API Calls

The tool automatically handles parameter resolution for nested API calls:

```bash
# Automatically fetches stack list, then events for matching stacks
awsquery cloudformation describe-stack-events production

# Three-level call: list stacks → get resources → filter results
awsquery cloudformation describe-stack-resources prod -- Lambda
```

### Parameter Passing (`-p`/`--parameter`)

Pass parameters directly to AWS API calls using the `-p` flag. This is useful for fine-tuning API behavior:

```bash
# Limit results for large responses
awsquery ec2 describe-instances -p MaxResults=20

# Filter specific resources by ID
awsquery ec2 describe-instances -p InstanceIds=i-1234567890abcdef0,i-0987654321fedcba0

# Multiple parameters (can use multiple -p flags)
awsquery elbv2 describe-load-balancers -p PageSize=10 -p Names=my-alb

# Complex parameter structures (for APIs like SSM)
awsquery ssm describe-parameters -p ParameterFilters=Key=Name,Option=Contains,Values=Ubuntu
```

**Parameter Format:**
- Simple: `Key=Value`
- Lists: `Key=Value1,Value2,Value3`
- Complex structures: Use semicolons to separate multiple objects (e.g., `Key1=Val1,Val2;Key2=Val3`)
- Type conversion: Numbers and booleans are automatically converted
- Nested structures: Comma-separated values within objects, semicolon-separated objects
- CloudTrail example: `LookupAttributes=AttributeKey=EventName,AttributeValue=Login;AttributeKey=Username,AttributeValue=admin`

### Hint-Based Resolution (`-i`/`--input`)

Guide multi-step parameter resolution with function/field/limit hints:

```bash
# Basic function hint - guides which list operation to use
awsquery cloudformation describe-stack-resources -i list-sta production

# Field extraction hint - specify exact field to extract
awsquery elbv2 describe-tags -i desc-clus:clusterarn prod

# Result limiting - control how many resources are processed (default: 10)
awsquery ssm get-parameters -i ::5  # Limit to 5 parameters
awsquery ec2 describe-instances -i ::20  # Limit to 20 instances
awsquery s3api list-objects -i ::0  # Unlimited (remove default limit)

# Field override without function (uses inferred function)
awsquery ecs describe-tasks -i :clusterarn  # Extract ClusterArn field

# Combined hints - function:field:limit
awsquery elbv2 describe-tags -i desc-clus:clusterarn:5  # Function + field + limit
awsquery rds describe-db-snapshots -i :arn:10  # Field + limit (inferred function)
```

**Hint Syntax:** `[function]:[field]:[limit]`
- **function**: Operation to use (e.g., "desc-clus", smart matching enabled)
- **field**: Specific field to extract (e.g., "arn", "clusterarn")
- **limit**: Max resources to process (e.g., "5", "10", "0" for unlimited)
- Any component can be omitted (e.g., "::5" for limit only, ":arn" for field only)

**Key Features:**
- **Smart matching**: "desc-inst" matches "describe-instances"
- **Field targeting**: Override default field extraction
- **Result limiting**: Default 10 items, configurable with ::N syntax
- **Flexible syntax**: Mix and match function/field/limit as needed

### Filtering Strategies

```bash
# All filters must match (AND logic), each using partial matching
# Finds instances where ALL three terms appear somewhere in the data
awsquery ec2 describe-instances production web database

# Column filters use partial, case-insensitive matching
# Shows columns containing "Instance", "State", or "Private" in their names
awsquery ec2 describe-instances -- Instance State Private

# Combine value and column filters
# Finds buckets with "backup" in any field, shows Name and Creation columns
awsquery s3 list-buckets backup -- Name Creation

# Partial matching examples:
# "prod" matches "production", "prod-server", "myproduct"
# "PROD" matches "production" (case-insensitive)
# "i-123" matches "i-1234567890abcdef0"
```

### Performance Tips

- Use specific filters to reduce API calls
- Column filters (`--`) don't affect API calls, only display
- Use `--region` to avoid cross-region latency
- Keys mode (`-k`) adds overhead; use only for discovery

## Troubleshooting

### Common Issues

**"No matching resources found"**
- Check your filters are not too restrictive
- Use debug mode (`-d`) to see actual API responses
- Verify you have permissions in the target region/account

**"Access Denied" errors**
- Ensure your AWS credentials have ReadOnly permissions
- Check if using the correct profile with `--profile`
- Verify the operation is permitted

**"Parameter validation failed"**
- Some APIs require specific parameters
- The tool attempts automatic resolution but may need manual input
- Use debug mode to see the parameter resolution process

**Performance issues**
- Large result sets may take time to process
- Use more specific filters to reduce data volume
- Consider using `--region` to target specific regions

**`awsquery: command not found` after `uv tool install`**
- Run `uv tool update-shell` and restart your shell; uv's bin directory (`~/.local/bin`) has to be on `PATH`
- `uv tool list` shows what is installed

**uvx keeps running an old version**
- `uvx awsquery` reuses the cached version; use `uvx awsquery@latest` to re-check PyPI
- `uv cache clean awsquery` drops the cached build entirely
- For an installed tool use `uv tool upgrade awsquery`

**Tab completion does not work**
- Completion needs a real executable on `PATH`: use `uv tool install awsquery`, not a `uvx` alias
- See [Enable Shell Autocomplete](#enable-shell-autocomplete)

## Requirements

- Python 3.10 or newer - or just [uv](https://docs.astral.sh/uv/), which supplies its own Python
- AWS credentials configured the same way the AWS CLI expects them

The package dependencies are:

- boto3>=1.35.0
- botocore>=1.35.0
- tabulate>=0.9.0
- argcomplete>=3.0.0
- PyYAML>=6.0.0

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please ensure tests pass and follow the existing code style.
