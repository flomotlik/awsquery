# Docker Usage Guide for awsquery

This document explains how to use Docker with the awsquery project, including both development and production environments.

## Docker Setup Overview

The project provides two Docker configurations:

1. **Development Environment** (`Dockerfile`) - Full development environment with testing tools
2. **Production Environment** (`Dockerfile.prod`) - Minimal production-ready container

## Quick Start

### Development Environment

```bash
# Build development container
make docker-build

# Open interactive shell with all dev tools
make shell

# Run tests in Docker
make test-in-docker
```

### Production Environment

```bash
# Build production container
make docker-build-prod

# Run awsquery command
docker-compose run --rm awsquery-prod ec2 describe-instances

# Test production container
make test-in-docker-prod
```

## Available Docker Services

### `awsquery-dev` (Development)
- **Purpose**: Development environment with all dependencies
- **Image**: Based on `python:3.11-slim`
- **Includes**: 
  - All development dependencies from `pyproject.toml[dev]`
  - Testing frameworks (pytest, coverage, etc.)
  - Code quality tools (black, flake8, mypy, etc.)
  - AWS CLI
  - Git for version control
- **Usage**: Interactive development, testing, debugging

### `awsquery-prod` (Production)
- **Purpose**: Minimal production environment
- **Image**: Based on `python:3.11-slim`
- **Includes**: 
  - Only production dependencies from `pyproject.toml`
  - AWS CLI
  - Non-root user for security
- **Usage**: Production deployments, CI/CD pipelines

### `awsquery` (Legacy)
- **Purpose**: Backward compatibility
- **Configuration**: Extends `awsquery-dev`

## Installation Methods

### Development Dependencies

The development Dockerfile installs all dependencies using:

```dockerfile
RUN pip install --no-cache-dir -e ".[dev]"
```

This installs:
- **Production dependencies**: boto3, botocore, tabulate, argcomplete
- **Development dependencies**: pytest, pytest-cov, black, flake8, mypy, etc.
- **Package in editable mode**: Changes to source code are reflected immediately

### Production Dependencies

The production Dockerfile installs minimal dependencies using:

```dockerfile
RUN pip install --no-cache-dir .
```

This installs only the dependencies listed in `pyproject.toml` `dependencies` section.

## Usage Examples

### Development Workflow

```bash
# Start development environment
docker-compose run --rm awsquery-dev

# Inside container - run tests
make test

# Run specific test category
make test-unit

# Check code coverage
make coverage

# Format code
make format

# Run linting
make lint

# Test original awsquery.py
python awsquery.py ec2 describe-instances --dry-run

# Test new modular CLI
awsquery ec2 describe-instances --dry-run
```

### Production Usage

```bash
# Run specific AWS queries
docker-compose run --rm awsquery-prod ec2 describe-instances
docker-compose run --rm awsquery-prod s3 list-buckets
docker-compose run --rm awsquery-prod cloudformation describe-stacks

# With filters and JSON output
docker-compose run --rm awsquery-prod ec2 describe-instances prod -- InstanceId State.Name
docker-compose run --rm awsquery-prod -j s3 list-buckets backup -- Name CreationDate
```

### AWS Credentials

AWS credentials are mounted from your local `~/.aws` directory:

```yaml
volumes:
  - ~/.aws:/root/.aws:ro  # Development (root user)
  - ~/.aws:/home/awsquery/.aws:ro  # Production (non-root user)
```

Environment variables are also supported:
- `AWS_PROFILE`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`
- `AWS_REGION`
- `AWS_DEFAULT_REGION`

## Available Make Targets

| Target | Description | Environment |
|--------|-------------|-------------|
| `docker-build` | Build development container | Development |
| `docker-build-prod` | Build production container | Production |
| `shell` | Open interactive shell | Development |
| `test-in-docker` | Run full test suite in Docker | Development |
| `test-in-docker-prod` | Test production container | Production |
| `docker-clean` | Clean up Docker resources | Both |

## File Structure in Container

### Development Container (`/app`)
```
/app/
├── pyproject.toml      # Project configuration
├── pytest.ini         # Test configuration
├── .coveragerc         # Coverage configuration
├── Makefile           # Development commands
├── policy.json        # Security policy
├── src/awsquery/      # Modular source code
├── tests/             # Test suite
└── awsquery.py        # Original script (backward compatibility)
```

### Production Container (`/app`)
```
/app/
├── pyproject.toml      # Project configuration
├── policy.json        # Security policy
├── src/awsquery/      # Modular source code
└── awsquery.py        # Original script (backward compatibility)
```

## Security Features

### Production Container Security
- **Non-root user**: Runs as `awsquery` user (UID 1000)
- **Read-only credentials**: AWS credentials mounted read-only
- **Minimal dependencies**: Only production packages installed
- **No development tools**: Reduces attack surface

### Development Container Security
- **Read-only credentials**: AWS credentials mounted read-only
- **Isolated environment**: Development dependencies contained
- **Volume mounts**: Source code changes reflected immediately

## Troubleshooting

### Common Issues

1. **AWS Credentials Not Found**
   ```bash
   # Ensure ~/.aws directory exists and contains credentials
   ls -la ~/.aws/
   
   # Test AWS CLI access
   docker-compose run --rm awsquery-dev aws sts get-caller-identity
   ```

2. **Permission Issues**
   ```bash
   # Check file permissions
   docker-compose run --rm awsquery-dev ls -la
   
   # For production container, ensure non-root user can access files
   docker-compose run --rm awsquery-prod whoami
   ```

3. **Module Import Errors**
   ```bash
   # Verify package installation
   docker-compose run --rm awsquery-dev pip show awsquery
   
   # Test both access methods
   docker-compose run --rm awsquery-dev python awsquery.py --help
   docker-compose run --rm awsquery-dev awsquery --help
   ```

### Debug Commands

```bash
# Check container contents
docker-compose run --rm awsquery-dev ls -la /app

# Verify Python environment
docker-compose run --rm awsquery-dev python -c "import awsquery; print('OK')"

# Check installed packages
docker-compose run --rm awsquery-dev pip list

# Test AWS CLI
docker-compose run --rm awsquery-dev aws --version
```

## CI/CD Integration

The production Docker image is ideal for CI/CD pipelines:

```yaml
# Example GitHub Actions usage
- name: Build and test awsquery
  run: |
    docker-compose build awsquery-prod
    docker-compose run --rm awsquery-prod --help
```

## Building Without Docker Compose

If you prefer to use Docker directly:

```bash
# Development
docker build -f Dockerfile -t awsquery:dev .
docker run -it --rm -v ~/.aws:/root/.aws:ro awsquery:dev

# Production  
docker build -f Dockerfile.prod -t awsquery:prod .
docker run --rm -v ~/.aws:/home/awsquery/.aws:ro awsquery:prod --help
```