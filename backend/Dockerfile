# RAG Ingestion Worker Dockerfile
# ARM64 compatible, CPU-only PyTorch for minimal image size (~1.7GB vs ~9.7GB)

FROM python:3.11-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libxcb1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
# CPU-only PyTorch — critical for image size
# The --extra-index-url ensures PyTorch downloads CPU-only wheels
# instead of the default CUDA-enabled ones (~8GB savings)
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copy application code
COPY ingestion.py .

# Create non-root user and images directory
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app \
    && mkdir -p /images && chown appuser:appuser /images \
    && mkdir -p /home/appuser/.cache && chown appuser:appuser /home/appuser/.cache
USER appuser

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run the ingestion worker
CMD ["python", "ingestion.py"]
