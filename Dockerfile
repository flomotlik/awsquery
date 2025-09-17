FROM python:3.11-slim

# Development Dockerfile optimized for volume mounts
# Only copies essential files needed for package installation
# Development files (scripts/, docs/, test analysis files) are excluded
# and will be available via volume mounts in docker-compose

# Install system dependencies
RUN apt-get update && apt-get install -y \
    make \
    curl \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI with architecture detection
RUN ARCH=$(uname -m) \
    && if [ "$ARCH" = "x86_64" ]; then \
        AWS_CLI_ARCH="x86_64"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        AWS_CLI_ARCH="aarch64"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi \
    && echo "Installing AWS CLI for architecture: $AWS_CLI_ARCH" \
    && curl "https://awscli.amazonaws.com/awscli-exe-linux-${AWS_CLI_ARCH}.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws/ \
    && aws --version

# Set working directory
WORKDIR /app

# Copy only essential files for package installation
COPY pyproject.toml .
COPY policy.json .

# Copy source code (minimal for installation)
COPY src/ ./src/

# Install the package with all dependencies
# Note: This installs from the copied source, but in development
# the volume mount will override this with live code
RUN pip install --no-cache-dir -e ".[dev]"

# Copy additional configuration files needed for testing/CI
# These will be overridden by volume mounts in development
COPY pytest.ini .
COPY .coveragerc .
COPY Makefile .

# Configure bash autocomplete for awsquery
RUN echo '# Enable awsquery autocomplete' >> /root/.bashrc \
    && echo 'eval "$(register-python-argcomplete awsquery)"' >> /root/.bashrc \
    && echo 'echo "awsquery autocomplete enabled. Try: awsquery <TAB>"' >> /root/.bashrc

# Set default command to bash for interactive use
ENTRYPOINT ["/bin/bash"]