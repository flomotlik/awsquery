FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    make \
    curl \
    unzip \
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

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY awsquery.py .
COPY policy.json .
COPY Makefile .

# Make awsquery executable
RUN chmod +x awsquery.py

# Create a symlink for easier access
RUN ln -s /app/awsquery.py /usr/local/bin/awsquery

# Set default command to bash for interactive use
ENTRYPOINT ["/bin/bash"]