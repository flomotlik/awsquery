FROM python:3.11-slim

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

# Copy project configuration files
COPY pyproject.toml .
COPY pytest.ini .
COPY .coveragerc .
COPY Makefile .
COPY policy.json .

# Copy source code and tests
COPY src/ ./src/
COPY tests/ ./tests/
COPY awsquery.py .

# Install the package with all dependencies (production + dev for testing)
RUN pip install --no-cache-dir -e ".[dev]"

# Make original awsquery.py executable for backward compatibility
RUN chmod +x awsquery.py

# Create symlinks for both access methods
RUN ln -sf /app/awsquery.py /usr/local/bin/awsquery-legacy \
    && ln -sf /usr/local/bin/awsquery /usr/local/bin/awsquery-cli

# Configure bash autocomplete for awsquery
RUN echo '# Enable awsquery autocomplete' >> /root/.bashrc \
    && echo 'eval "$(register-python-argcomplete awsquery)"' >> /root/.bashrc \
    && echo 'echo "awsquery autocomplete enabled. Try: awsquery <TAB>"' >> /root/.bashrc

# Set default command to bash for interactive use
ENTRYPOINT ["/bin/bash"]