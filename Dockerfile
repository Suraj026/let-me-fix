FROM python:3.12-slim

WORKDIR /workspace

# Install git for patch apply
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install pytest for running tests
RUN pip install --no-cache-dir pytest

# Default command: keep container alive for exec
CMD ["sleep", "infinity"]

