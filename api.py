"""
api.py  —  FastAPI application for the GitHub Visualizer pipeline.

Endpoints:
  POST /analyze              — run the full analysis pipeline
  POST /analyze/html         — same, returns HTML viewer directly

  POST /chat                 — single-turn RAG chat (JSON response)
  POST /chat/stream          — single-turn RAG chat (SSE streaming)
  GET  /chat/sessions        — list active sessions
  DELETE /chat/sessions/{id} — clear a session's history

  GET  /health               — liveness probe
  GET  /readiness            — readiness probe
  GET  /docs                 — Swagger UI (built-in)
"""
from __future__ import annotations

import json
import os
import tempfile
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from pipeline import build_pipeline
from chat import answer, answer_stream


app = FastAPI(
    title="GitHub Visualizer",
    description=(
        "Multi-agent LangGraph pipeline that analyses a GitHub repository "
        "and lets you chat with it via RAG over Endee vector indexes."
    ),
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline = None
_executor = ThreadPoolExecutor(max_workers=int(os.getenv("WORKERS", "2")))

# In-memory session store: {session_id: [{role, content}, ...]}
# For production replace with Redis (see README)
_sessions: dict[str, list[dict]] = defaultdict(list)


@app.on_event("startup")
async def _startup():
    global _pipeline
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    endee_url  = os.getenv("ENDEE_BASE_URL")

    _check_endee(endee_url)

    _pipeline  = build_pipeline(groq_model=groq_model, endee_base_url=endee_url)
    print(f"[startup] Pipeline ready  model={groq_model}")


def _check_endee(endee_url: str | None) -> None:
    """Fail fast with a clear message if Endee is unreachable."""
    import urllib.request, urllib.error
    from endee import Endee

    base = (endee_url or "http://localhost:8080/api/v1").rstrip("/")
    ping_url = f"{base}/indexes"
    print(f"[startup] Checking Endee at {ping_url} ...")

    try:
        with urllib.request.urlopen(ping_url, timeout=5):
            pass
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError(
                f"[startup] Endee returned HTTP {e.code} — check your ENDEE_API_KEY. "
                f"URL: {ping_url}"
            )
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(
            f"[startup] Cannot reach Endee at {ping_url}  {e}\n"
        )

    try:
        client = Endee()
        if endee_url:
            client.set_base_url(endee_url)
        client.list_indexes()
        print("[startup] Endee connection OK ✓")
    except Exception as e:
        raise RuntimeError(
            f"[startup] Endee SDK error: {e}\n"
            f"Run  python diagnose_endee.py  for details."
        )



def _groq_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

def _endee_url() -> str | None:
    return os.getenv("ENDEE_BASE_URL") or None


class AnalyzeRequest(BaseModel):
    repo_url:   str
    groq_model: Optional[str] = None

    @field_validator("repo_url")
    @classmethod
    def must_be_github(cls, v: str) -> str:
        if "github.com" not in v:
            raise ValueError("repo_url must be a github.com URL")
        return v.rstrip("/")


class AnalyzeResponse(BaseModel):
    repo_name:      str
    explanation:    str
    mermaid_code:   str
    flowchart_html: str


class ChatRequest(BaseModel):
    repo_name:  str              # e.g. "tiangolo/fastapi"
    question:   str
    session_id: Optional[str] = None   # pass to maintain conversation history
    groq_model: Optional[str] = None

    @field_validator("question")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question cannot be empty")
        return v.strip()

    @field_validator("repo_name")
    @classmethod
    def valid_repo(cls, v: str) -> str:
        v = v.strip().lstrip("https://github.com/").lstrip("/")
        return v


class CitationItem(BaseModel):
    file:       str
    source:     str   # "code" | "text"
    similarity: float


class ChatResponse(BaseModel):
    session_id: str
    answer:     str
    citations:  list[CitationItem]



@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}


@app.get("/readiness", tags=["ops"])
async def readiness():
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    return {"status": "ready"}


@app.post("/analyze", response_model=AnalyzeResponse, tags=["pipeline"])
async def analyze(req: AnalyzeRequest):
    """
    Analyse a GitHub repository — clone, embed, explain, and generate flowchart.
    Returns explanation text, Mermaid source, and a full HTML viewer.
    Typical latency: 60–120 s.
    """
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready yet")

    pipeline = (
        build_pipeline(groq_model=req.groq_model, endee_base_url=_endee_url())
        if req.groq_model else _pipeline
    )

    output_dir = tempfile.mkdtemp(prefix="ghviz_out_")
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        final_state = await loop.run_in_executor(
            _executor,
            lambda: pipeline.invoke({"repo_url": req.repo_url, "output_dir": output_dir}),
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))

    html_path = final_state.get("flowchart_path", "")
    try:
        from pathlib import Path
        flowchart_html = Path(html_path).read_text(encoding="utf-8")
    except Exception:
        flowchart_html = ""

    return AnalyzeResponse(
        repo_name=final_state.get("repo_name", ""),
        explanation=final_state.get("explanation", ""),
        mermaid_code=final_state.get("mermaid_code", ""),
        flowchart_html=flowchart_html,
    )


@app.post("/analyze/html", response_class=HTMLResponse, tags=["pipeline"])
async def analyze_html(req: AnalyzeRequest):
    """Same as POST /analyze but returns the flowchart HTML directly."""
    result = await analyze(req)
    return HTMLResponse(content=result.flowchart_html)



@app.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(req: ChatRequest):
    """
    Ask a question about a previously-analysed GitHub repository.

    The repo must have been analysed first via POST /analyze so its vectors
    exist in Endee. Pass `session_id` from a previous response to continue
    a multi-turn conversation with memory.

    **Flow:**
    1. Embed the question locally (Sentence Transformers)
    2. Query both Endee indexes (code + text) for the repo
    3. Feed top snippets + conversation history to Groq
    4. Return the answer with source citations
    """
    session_id = req.session_id or str(uuid.uuid4())
    history    = _sessions[session_id]

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        ans, snippets = await loop.run_in_executor(
            _executor,
            lambda: answer(
                question=req.question,
                repo_name=req.repo_name,
                history=history,
                endee_url=_endee_url(),
                groq_model=req.groq_model or _groq_model(),
            ),
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))

    # Persist turn to session history
    _sessions[session_id].append({"role": "user",      "content": req.question})
    _sessions[session_id].append({"role": "assistant",  "content": ans})

    # Trim history to last 20 messages to avoid unbounded growth
    _sessions[session_id] = _sessions[session_id][-20:]

    return ChatResponse(
        session_id=session_id,
        answer=ans,
        citations=[
            CitationItem(file=s["file"], source=s["source"], similarity=s["similarity"])
            for s in snippets[:8]
        ],
    )


@app.post("/chat/stream", tags=["chat"])
async def chat_stream(req: ChatRequest):
    """
    Same as POST /chat but streams the answer token-by-token via
    Server-Sent Events (SSE).

    SSE event format:
    ```
    event: citations
    data: [{"file": "...", "source": "code", "similarity": 0.92}, ...]

    data: Hello<br>

    data: , here is the answer...

    data: [DONE]
    ```

    First event is always `citations` (JSON array of sources).
    Subsequent `data:` events are answer tokens (newlines encoded as `<br>`).
    Final event is `data: [DONE]`.

    Pass `session_id` in the request body to maintain conversation history.
    The session is updated server-side as the stream completes.
    """
    session_id = req.session_id or str(uuid.uuid4())
    history    = list(_sessions[session_id])   # snapshot for this request

    full_answer_parts: list[str] = []

    def _generate():
        """Run streaming generator and collect full answer for history."""
        for event in answer_stream(
            question=req.question,
            repo_name=req.repo_name,
            history=history,
            endee_url=_endee_url(),
            groq_model=req.groq_model or _groq_model(),
        ):
            if event.startswith("data: ") and not event.startswith("data: [DONE]") \
                    and not event.startswith("event:"):
                token = event[6:].replace("<br>", "\n").rstrip("\n")
                full_answer_parts.append(token)
            yield event

        full_answer = "".join(full_answer_parts)
        _sessions[session_id].append({"role": "user",      "content": req.question})
        _sessions[session_id].append({"role": "assistant",  "content": full_answer})
        _sessions[session_id] = _sessions[session_id][-20:]

        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering":"no",       # disable nginx buffering
            "X-Session-Id":     session_id, # also in header for easy access
        },
    )



@app.get("/chat/sessions", tags=["chat"])
async def list_sessions():
    """List all active chat sessions and their message counts."""
    return {
        sid: {"message_count": len(msgs)}
        for sid, msgs in _sessions.items()
    }


@app.delete("/chat/sessions/{session_id}", tags=["chat"])
async def clear_session(session_id: str):
    """Clear the conversation history for a session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del _sessions[session_id]
    return {"deleted": session_id}
