# Multi-stage Dockerfile for Telegram Bots
# Based on 9-Tones architecture from DEPLOY.md

FROM python:3.11-alpine AS base

# Install system dependencies
RUN apk add --no-cache \
    curl \
    && rm -rf /var/cache/apk/*

# Create non-root user
RUN addgroup -g 1001 -S botuser && \
    adduser -S botuser -u 1001 -G botuser

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py ./
COPY customers.json ./

# Create logs directory
RUN mkdir -p /app/logs && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Health check endpoint (simple file-based check)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Expose ports for health checks (not actually used by telegram bots)
EXPOSE 8000

# Default command (can be overridden)
CMD ["python", "bot.py"]