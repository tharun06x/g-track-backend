FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching — only rebuilds when deps change)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application source
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose port
EXPOSE 8000

# Health check used by Docker and Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production command (Issue 16 fix):
#
# Why gunicorn + UvicornWorker instead of plain uvicorn?
#   - Gunicorn provides proper UNIX signal handling, graceful shutdown,
#     worker recycling on memory leaks, and structured process management.
#   - UvicornWorker gives us asyncio's full concurrency within that worker.
#
# Why -w 1 (single worker) on Render Free Tier?
#   - Each worker maintains its own DB connection pool.
#   - 2 workers × pool_size=3 = 6 persistent DB connections consumed always.
#   - Render free PostgreSQL limit is 25 total connections.
#   - One async worker handles hundreds of concurrent I/O-bound requests
#     efficiently without the extra connection and memory overhead.
CMD ["gunicorn", "main:app", \
     "-w", "1", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--log-level", "info"]