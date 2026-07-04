# Dockerfile
# ----------
# Build image for VM metadata exporter sidecars.
#
# supercronic is used as a lightweight cron daemon that runs in the
# foreground, logs to stdout, and does not require an init system.
#
# Usage:
#   docker compose build
#   docker compose up -d

FROM python:3.12-slim

ARG SUPERCRONIC_VERSION=0.2.29
ARG SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64

# Install supercronic
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && curl -fsSL "${SUPERCRONIC_URL}" -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code and scripts
COPY app/ /app/
# COPY scripts/ /app/scripts/
# RUN chmod +x /app/scripts/*.sh

WORKDIR /app

# Crontab is mounted per sidecar at runtime
CMD ["supercronic", "/crontab"]
