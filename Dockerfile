# Multi-stage or slim python container for Streamlit Application
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and sample data
COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY app.py pytest.ini ./

# Pre-generate sample guide and build local search index
RUN python scripts/generate_sample_pdf.py && python scripts/build_guidelines_index.py

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
