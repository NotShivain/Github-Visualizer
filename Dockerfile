# ── Stage 1: dependency cache ─────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

# System deps needed for git, sentence-transformers, and compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir fastapi uvicorn[standard] pydantic

# Pre-download Sentence Transformer model weights so they're baked into the
# image (avoids cold-start downloads in production).
# Both models output 768-dim vectors.
RUN python - << 'EOF'
from sentence_transformers import SentenceTransformer
print("Downloading text model...")
SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
print("Downloading code model...")
SentenceTransformer("flax-sentence-embeddings/st-codesearch-distilroberta-base")
print("Models cached.")
EOF

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Only runtime system deps (git for cloning, libgomp for torch/ST)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
# Copy cached HuggingFace model weights
COPY --from=deps /root/.cache /root/.cache

# Copy application source
COPY . .

# ── Runtime config ────────────────────────────────────────────────────────────
# Required secrets — must be injected at runtime (env vars or Key Vault ref)
ENV GROQ_API_KEY=""
ENV ENDEE_API_KEY=""

# Optional overrides
ENV GROQ_MODEL="llama-3.3-70b-versatile"
ENV ENDEE_BASE_URL=""
ENV WORKERS="2"

# Uvicorn config
ENV HOST="0.0.0.0"
ENV PORT="8000"

EXPOSE 8000

# Non-root user for security
RUN useradd -m -u 1000 appuser \
 && chown -R appuser:appuser /app \
 && chown -R appuser:appuser /root/.cache || true
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["sh", "-c", "uvicorn api:app --host $HOST --port $PORT --workers 1 --timeout-keep-alive 120"]
