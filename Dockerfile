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

FROM python:3.12-alpine

COPY bin/supercronic /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic

# Install Python dependencies
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code and scripts
COPY app/ /app/
# COPY scripts/ /app/scripts/
# RUN chmod +x /app/scripts/*.sh

WORKDIR /app

# Crontab is mounted per sidecar at runtime
CMD ["/usr/local/bin/supercronic", "/crontab"]
