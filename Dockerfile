# Chatterbox Shorts Pipeline — CPU-only production image
FROM python:3.12-slim-bookworm

# ── System dependencies ───────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────
WORKDIR /app

# Install PyTorch CPU-only first (keeps image under 2 GB instead of 5+ GB with CUDA)
RUN pip install --no-cache-dir \
    torch==2.7.0 \
    torchaudio==2.7.0 \
    --index-url https://download.pytorch.org/whl/cpu

# Core TTS & pipeline deps
COPY requirements.txt requirements_shorts.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements_shorts.txt \
    && pip install --no-cache-dir fastapi uvicorn python-multipart

# Pre-download NLTK data
RUN python -c "import nltk; nltk.download('punkt_tab', quiet=True)"

# ── Application code ──────────────────────────────────────────────
COPY chatterbox/ ./chatterbox/
COPY reddit_shorts/ ./reddit_shorts/
COPY scripts/ ./scripts/
COPY run_shorts_pipeline.py .
COPY api_server.py .

# ── Runtime ───────────────────────────────────────────────────────
EXPOSE 8000

# Persistent volumes (mount from host)
VOLUME ["/app/voice_profiles", "/app/video_clips", "/app/output"]

ENV PYTHONUNBUFFERED=1

# Default: API server (override for one-shot CLI runs)
CMD ["python", "api_server.py"]
