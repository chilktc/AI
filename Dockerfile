# Mind-Log AI Docker Image — Multi-stage build
# Stage 1: Builder — install compile dependencies and Python packages
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Runtime — lean image with only what's needed
FROM python:3.11-slim

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p logs data/cache data/outputs \
    && chown -R appuser:appuser /app

# Copy only the directories needed at runtime.
# prompts/ is intentionally excluded — it is mounted as a volume at deploy time
# so prompt versions can be updated without rebuilding the image.
COPY src/ src/
COPY config/ config/
COPY langgraph.json langgraph.json

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

USER appuser

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
