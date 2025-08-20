FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    python3-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash orderapp
WORKDIR /orderapp

RUN python -m venv /orderapp/venv
ENV PATH="/orderapp/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=orderapp:orderapp orderapp.py .

RUN mkdir -p /orderapp/logs && chown orderapp:orderapp /orderapp/logs

USER orderapp

ENV SHEET_NAME="9_ტონა_ფული"
ENV WORKSHEET_NAME_ORDERS="orders"
ENV MESSAGE_COOLDOWN="5"
ENV PENDING_ORDER_TIMEOUT="300"
ENV CLEANUP_INTERVAL="600"
ENV MAX_RETRIES="3"
ENV RETRY_DELAY="2"

CMD ["python", "orderapp.py"]