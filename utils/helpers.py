"""
utils/helpers.py  —  Shared helpers used across agents.
"""
from __future__ import annotations
import hashlib
from typing import Optional
import re
from dotenv import load_dotenv

load_dotenv()
# ── Groq LLM factory ─────────────────────────────────────────────────────────

def get_groq_client():
    """Return a configured Groq client (uses GROQ_API_KEY env var)."""
    from groq import Groq
    return Groq()


def groq_chat(
    messages: list[dict],
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """
    Send a chat request to Groq and return the assistant message text.

    Default model is *llama-3.3-70b-versatile*. Other good options:
      - "llama3-70b-8192"          (Llama 3 70B, 8k context)
      - "llama-3.1-8b-instant"     (very fast, lighter tasks)
      - "mixtral-8x7b-32768"       (32k context, good for long files)
      - "gemma2-9b-it"             (Google Gemma 2 9B)
    """
    client = get_groq_client()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ── Endee client factory ─────────────────────────────────────────────────────

def get_endee_client(base_url: Optional[str] = None):
    """Return a configured Endee client."""
    from endee import Endee
    client = Endee()
    if base_url:
        client.set_base_url(base_url)
    return client


def ensure_index(
    client,
    name: str,
    dimension: int = 768,
    space_type: str = "cosine",
    precision: str = "float32",
    retries: int = 3,
):
    """Get or create an Endee index, with retries on transient errors.

    Endee's list_indexes() returns a plain list of index name strings.
    create_index() precision options: float32 | float16 | int8d | int16d | binary
    """
    import time

    # ── 1. Check existing indexes ─────────────────────────────────────────────
    try:
        raw = client.list_indexes()
        existing: set[str] = set()
        for item in raw:
            if isinstance(item, str):
                existing.add(item)
            elif isinstance(item, dict):
                existing.add(item.get("name", ""))
    except Exception:
        existing = set()

    if name in existing:
        return client.get_index(name=name)

    # ── 2. Create with retries ────────────────────────────────────────────────
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client.create_index(
                name=name,
                dimension=dimension,
                space_type=space_type,
                precision=precision,
            )
            return client.get_index(name=name)

        except Exception as e:
            err = str(e).lower()

            # Already exists (race condition / previous run) — just open it
            if "conflict" in err or "already exists" in err:
                print(f"  [endee] Index '{name}' already exists, reusing.")
                return client.get_index(name=name)

            # Transient "Unknown Error" — retry with backoff
            if "unknown error" in err or "try again" in err:
                wait = 2 ** attempt
                print(f"  [endee] Transient error on attempt {attempt}/{retries}, "
                      f"retrying in {wait}s ... ({e})")
                time.sleep(wait)
                last_exc = e
                continue

            # Any other error (bad name, bad dimension, auth) — fail immediately
            raise

    raise RuntimeError(
        f"Failed to create Endee index '{name}' after {retries} attempts. "
        f"Last error: {last_exc}\n\n"
        f"Run  python diagnose_endee.py  for a full connectivity report."
    ) from last_exc



# ── Sentence Transformers embedding helpers ───────────────────────────────────
#
# Models are loaded once and cached in a module-level dict.
# All inference runs locally — no API key required.
#
# Text : "sentence-transformers/all-mpnet-base-v2"        → 768 dims
#        "sentence-transformers/all-MiniLM-L6-v2"         → 384 dims (faster)
# Code : "flax-sentence-embeddings/st-codesearch-distilroberta-base" → 768 dims
#        (proper ST-native code search model, unlike codebert-base which is
#         a masked-LM and must be wrapped — this one works out of the box)

_MODEL_CACHE: dict[str, object] = {}

TEXT_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
CODE_EMBEDDING_MODEL = "flax-sentence-embeddings/st-codesearch-distilroberta-base"
EMBEDDING_DIM        = 768   # both models output 768 dims


def _load_model(model_name: str):
    """Lazily load and cache a SentenceTransformer model."""
    if model_name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer
        print(f"  [embed] Loading model '{model_name}' (first run downloads weights) ...")
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


def get_embeddings(
    texts: list[str],
    model_name: str = TEXT_EMBEDDING_MODEL,
) -> list[list[float]]:
    """Generate embeddings locally using Sentence Transformers."""
    if not texts:
        return []
    model = _load_model(model_name)
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return vectors.tolist()


def get_code_embeddings(texts: list[str]) -> list[list[float]]:
    """Code-aware embeddings; falls back to text model on any error."""
    try:
        return get_embeddings(texts, model_name=CODE_EMBEDDING_MODEL)
    except Exception as e:
        print(f"  [embed] Code model failed ({e}), falling back to text model.")
        return get_embeddings(texts, model_name=TEXT_EMBEDDING_MODEL)


# ── Text chunking ─────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Split text into overlapping word-level chunks."""
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks


def chunk_code(source: str, max_lines: int = 60) -> list[str]:
    """Split source code into chunks of at most max_lines, breaking on blank lines."""
    lines = source.splitlines()
    chunks, current = [], []
    for line in lines:
        current.append(line)
        if len(current) >= max_lines and line.strip() == "":
            chunks.append("\n".join(current))
            current = []
    if current:
        chunks.append("\n".join(current))
    return chunks or [source]


# ── Misc ──────────────────────────────────────────────────────────────────────

def stable_id(prefix: str, text: str) -> str:
    """Generate a stable short ID from a prefix + content hash."""
    digest = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{prefix}_{digest}"


def truncate(text: str, max_chars: int = 12_000) -> str:
    """Hard-truncate text to max_chars characters."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def slugify(name: str) -> str:
    """
    Convert a repo name (or any string) into a valid Endee index name.
    Endee requires: alphanumeric + underscores only.

    Examples:
      "NotShivain/Resume-Analysis" -> "NotShivain_Resume_Analysis"
      "my-org/cool.project"        -> "my_org_cool_project"
    """
    # Replace any non-alphanumeric character (including / - .) with underscore
    slug = re.sub(r'[^A-Za-z0-9]+', '_', name)
    # Strip leading/trailing underscores
    slug = slug.strip('_')
    return slug
