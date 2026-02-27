# GitHub Visualizer

> **Built with [Endee](https://endee.io) — a high-performance vector database.**
> This project was built as a demonstration of Endee's capabilities as a vector store for a production AI pipeline. Endee is used as the sole vector database for storing and retrieving code and documentation embeddings across the entire multi-agent system.

---

A multi-agent AI system that analyses any GitHub repository and produces an interactive architecture diagram, a natural-language explanation of the codebase, and a RAG-powered chat interface that lets you ask questions directly about the code — all powered by Groq LLMs, Sentence Transformers, and Endee vector search.

**⚠️ Azure deployment is currently in progress.** The application is being containerised and deployed to Azure Container Apps. Run instructions below are for local development.

---

## Table of Contents

- [Why Endee](#-why-endee)
- [Architecture](#-architecture)
- [Features](#-features)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
  - [1. Start the Endee vector database](#1-start-the-endee-vector-database)
  - [2. Set environment variables](#2-set-environment-variables)
  - [3. Install Python dependencies](#3-install-python-dependencies)
  - [4. Start the FastAPI server](#4-start-the-fastapi-server)
  - [5. Open the frontend](#5-open-the-frontend)
- [Environment Variables](#-environment-variables)
- [API Reference](#-api-reference)
- [Project Structure](#-project-structure)
- [Deployment](#-deployment)

---

## ⬡ Why Endee

Endee is the vector database at the heart of this project. Every embedding produced by the pipeline — code chunks, README sections, documentation fragments — is stored and retrieved via Endee's API.

**How Endee is used in this project:**

| Stage | Endee usage |
|---|---|
| `code_analyzer` | Upserts code chunk embeddings into a per-repo `code_<repo>` index |
| `text_analyzer` | Upserts README/docs embeddings into a per-repo `text_<repo>` index |
| `retriever_agent` | Queries both indexes with targeted questions to gather synthesis context |
| `chat.py` (RAG) | Embeds every user question and queries both indexes in real time to ground LLM answers in actual source code |

**Why Endee over alternatives:**

- **Self-hosted Docker image** — `endeeio/endee-server:latest` runs locally with a single `docker run` command, zero infrastructure overhead during development
- **Simple HTTP API** — the Python SDK wraps clean REST endpoints; easy to introspect and debug
- **Per-repo index isolation** — each analysed repository gets its own dedicated indexes, keeping retrieval precise and preventing cross-repo contamination
- **Cosine similarity search** — embeddings are stored with `float32` precision and queried with HNSW (`ef=128`) for high-recall nearest-neighbour retrieval

---

## Architecture

```
GitHub URL
    │
    ▼
clone_agent  ──────────────────────────────────────────────┐
    │                                                       │
    ├──────────────────────────────────┐                    │
    ▼                   ▼             ▼                     │
code_analyzer    text_analyzer   dependency_analyzer        │
(embed → Endee)  (embed → Endee)  (AST import graph)       │
    │                   │             │                     │
    └───────────────────┴─────────────┘                     │
                        ▼                                   │
                  retriever_agent                           │
                  (query Endee indexes)                     │
                        │                                   │
                        ▼                                   │
                  synthesizer_agent   ◄─── Groq LLM         │
                  (explanation.md)                          │
                        │                                   │
                        ▼                                   │
                  flowchart_agent     ◄─── Groq LLM         │
                  (Mermaid diagram)                         │
                        │                                   │
                        ▼                                   │
                  renderer_agent                            │
                  (HTML + .mmd + .md)  ◄────────────────────┘
```

Chat is a separate RAG loop that runs on demand: user question → embed → query Endee → Groq → streamed answer.

---

## Features

- **Architecture diagram** — Mermaid flowchart with subgraphs, auto-rendered in the browser with zoom/pan and SVG export
- **Natural language explanation** — LLM-generated breakdown of architecture, data flow, entry points, and technology stack
- **RAG chat** — ask any question about the codebase; answers are grounded in retrieved code and doc snippets with source citations
- **Streaming responses** — chat answers stream token-by-token via Server-Sent Events
- **Session memory** — multi-turn conversation history per session
- **Self-contained frontend** — single HTML file, no build step, works with Live Server

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Tested on 3.11 and 3.13 |
| Docker Desktop | For running Endee locally |
| Groq API key | Free tier available at [console.groq.com](https://console.groq.com) |
| Endee API key | required even for self-hosted for authentication, you can set it anything as you like|
| VS Code + Live Server | Or any static file server for the frontend |

---

## Quick Start

### 1. Start the Endee vector database

Pull and run the official Endee Docker image:

```bash
docker run -d \
  --name endee \
  -p 8080:8080 \
  -v endee_data:/data \
  endeeio/endee-server:latest
```

On **Windows PowerShell**:

```powershell
docker run -d `
  --name endee `
  -p 8080:8080 `
  -v endee_data:/data `
  endeeio/endee-server:latest
```

Verify it's running:

```bash
curl http://localhost:8080/api/v1/indexes
# Expected: [] or a JSON array of existing indexes
```

> The `-v endee_data:/data` flag mounts a named volume so your vector indexes persist across container restarts. Remove it if you want a fresh start every time.

---

### 2. Set environment variables

Copy the example file and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
GROQ_API_KEY=gsk_...          # from console.groq.com
ENDEE_API_KEY=...              # from endee.io
ENDEE_BASE_URL=http://localhost:8080/api/v1
```

Then load the variables into your shell.

**Windows PowerShell:**

```powershell
$env:GROQ_API_KEY   = "gsk_..."
$env:ENDEE_API_KEY  = "..."
$env:ENDEE_BASE_URL = "http://localhost:8080/api/v1"
```

**Windows CMD:**

```cmd
set GROQ_API_KEY=gsk_...
set ENDEE_API_KEY=...
set ENDEE_BASE_URL=http://localhost:8080/api/v1
```

**macOS / Linux:**

```bash
export GROQ_API_KEY=gsk_...
export ENDEE_API_KEY=...
export ENDEE_BASE_URL=http://localhost:8080/api/v1
```

> **If Endee is behind an ngrok tunnel** set `ENDEE_BASE_URL` to your ngrok URL:
> ```
> ENDEE_BASE_URL=https://your-subdomain.ngrok-free.dev/api/v1
> ```

---

### 3. Install Python dependencies

```bash
cd "C:\Projects\Github Visualizer"

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

> **First run note:** the first analysis downloads ~750 MB of Sentence Transformer model weights (`all-mpnet-base-v2` and `st-codesearch-distilroberta-base`). This happens once and is cached locally. Subsequent runs are instant.

---

### 4. Start the FastAPI server

```bash
uvicorn api:app --reload --port 8000
```

You should see:

```
[startup] Checking Endee at http://localhost:8080/api/v1/indexes ...
[startup] Endee connection OK ✓
[startup] Pipeline ready  model=llama-3.3-70b-versatile
INFO:     Uvicorn running on http://127.0.0.1:8000
```

If Endee is not reachable the server will print a clear error. You can also run the diagnostics script independently:

```bash
python diagnose_endee.py
```

Interactive API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### 5. Open the frontend

**Option A — VS Code Live Server (recommended):**

1. Install the [Live Server extension](https://marketplace.visualstudio.com/items?itemName=ritwickdey.LiveServer) in VS Code
2. Right-click `frontend.html` in the Explorer panel
3. Select **Open with Live Server**
4. The UI opens at `http://127.0.0.1:5500/frontend.html`

**Option B — Python's built-in server:**

```bash
python -m http.server 5500
# Open http://localhost:5500/frontend.html
```

**Option C — Open directly:**

Double-click `frontend.html`. Works for most features, but streaming chat may be blocked by browser CORS policies on `file://` URLs — Live Server is preferred.

---

**Using the UI:**

1. Confirm the **API** field top-right shows `http://localhost:8000`
2. Paste a GitHub URL (e.g. `https://github.com/tiangolo/fastapi`)
3. Click **▶ Analyze** or press Enter — pipeline runs in 60–120 s
4. Explore the **Flowchart**, **Explanation**, and **Mermaid Source** tabs
5. Ask questions in the chat panel on the right

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ | — | Groq API key from console.groq.com |
| `ENDEE_API_KEY` | ✅ | — | Endee API key from endee.io |
| `ENDEE_BASE_URL` | ✅ | — | Full URL to Endee API e.g. `http://localhost:8080/api/v1` |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model for all LLM calls |
| `WORKERS` | No | `2` | ThreadPoolExecutor concurrency |
| `PORT` | No | `8000` | Port uvicorn listens on |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/readiness` | Readiness probe |
| `POST` | `/analyze` | Run full pipeline, returns JSON |
| `POST` | `/analyze/html` | Run full pipeline, returns HTML viewer |
| `POST` | `/chat` | Single-turn RAG chat, returns JSON |
| `POST` | `/chat/stream` | Streaming RAG chat via SSE |
| `GET` | `/chat/sessions` | List active sessions |
| `DELETE` | `/chat/sessions/{id}` | Clear a session |

Full interactive docs at `http://localhost:8000/docs`.

**Analyze a repo:**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/tiangolo/fastapi"}'
```

**Chat:**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "repo_name": "tiangolo/fastapi",
    "question": "How does dependency injection work in this codebase?"
  }'
```

---

## Project Structure

```
github-visualizer/
│
├── api.py                    # FastAPI app — all HTTP endpoints
├── pipeline.py               # LangGraph graph definition
├── state.py                  # Shared TypedDict state schema
├── chat.py                   # RAG chat engine (retrieve → LLM → stream)
├── main.py                   # CLI entry point
├── frontend.html             # Single-file UI — open with Live Server
├── requirements.txt
├── Dockerfile
├── .dockerignore
│
├── agents/
│   ├── clone_agent.py        # git clone --depth=1 to temp dir
│   ├── code_analyzer.py      # embed source files → Endee code index
│   ├── text_analyzer.py      # embed README/docs → Endee text index
│   ├── dependency_analyzer.py# AST import graph + entry point detection
│   ├── retriever_agent.py    # query Endee, de-duplicate, rank snippets
│   ├── synthesizer_agent.py  # Groq → natural language explanation
│   ├── flowchart_agent.py    # Groq → Mermaid diagram + sanitizer
│   └── renderer_agent.py     # write explanation.md, .mmd, .html
│
├── utils/
│   └── helpers.py            # Groq client, Endee client, ST embeddings,
│                             # chunking, slugify, ensure_index (with retry)
```

---

## Deployment

> **🚧 Azure deployment is currently in progress.**

The application is being deployed to **Azure Container Apps** with the following setup:

- `endee-server` — pulled directly from Docker Hub (`endeeio/endee-server:latest`), internal-only ingress, backed by an Azure File Share for index persistence
- `github-visualizer` — application image pushed to Azure Container Registry, public HTTPS ingress

Both containers run in the same Container Apps Environment and communicate over the private internal network at `http://endee-server:8080/api/v1`.
The Application Image is already available on docker hub, visit `https://hub.docker.com/repository/docker/notshivain/githubvisualizer/general`

Built with ❤️ By Shivain
