FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/datasets \
    OUTPUT_DIR=/app/outputs
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY datasets/ /app/datasets/
COPY solutions/submissions/sanjay_subair/ /app/solutions/submissions/sanjay_subair/

ENTRYPOINT ["python", "/app/solutions/submissions/sanjay_subair/02_sql_and_viz/etl_starter.py"]
