# Python 3.11 slim base
FROM python:3.11-slim

WORKDIR /app

# Build tools for packages without wheels (lxml fallback, native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY tests/ ./tests/
COPY pyproject.toml .
COPY README.md .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Run as a non-root user. Pre-create writable output dirs and hand them over.
RUN mkdir -p data reports logs \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Liveness: the package imports cleanly (catches a broken image/dep early).
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import stock_analysis"]

# Default command
CMD ["python", "-m", "stock_analysis.main", "--help"]
