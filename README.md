# GitHub Visualizer

**Multi-agent LangGraph pipeline** that analyses any GitHub repository and produces:
- 📄 A **detailed Markdown explanation** (architecture, data-flow, tech stack, key components)
- 🔷 An **interactive Mermaid flowchart** (standalone HTML with zoom/pan controls)

Built with **LangGraph** (agent orchestration), **Groq** (LLM inference), **Sentence Transformers** (local embeddings), and **Endee** (vector database).

> **APIs required:**
> - 🤖 **LLM calls** → [Groq](https://console.groq.com) (`GROQ_API_KEY`)
> - 🔢 **Embeddings** → Sentence Transformers — runs **fully locally**, no API key needed
>   - Text: `all-mpnet-base-v2` (768 dims) — high quality general embeddings
>   - Code: `microsoft/codebert-base` (768 dims) — code-aware, understands syntax & semantics

---

## Architecture

```
clone → [code_analyzer ║ text_analyzer ║ dependency_analyzer]
                        → retriever → synthesizer → flowchart → renderer
```

### Agents

| Agent | File | Responsibility |
|---|---|---|
| Clone | `agents/clone_agent.py` | `git clone --depth=1` the target repo |
| Code Analyzer | `agents/code_analyzer.py` | Parse source files, chunk, embed with **CodeBERT** (local), upsert to Endee; Groq generates structural summary |
| Text Analyzer | `agents/text_analyzer.py` | Parse README / Markdown docs, chunk, embed with **all-mpnet-base-v2** (local), upsert to Endee; Groq generates docs summary |
| Dependency Analyzer | `agents/dependency_analyzer.py` | Static import graph via AST (Python) and regex (JS/TS/Go/etc.); Groq generates dependency summary |
| Retriever | `agents/retriever_agent.py` | Build targeted queries from summaries, search Endee, de-duplicate results |
| Synthesizer | `agents/synthesizer_agent.py` | Feed all context to Groq → full Markdown explanation |
| Flowchart | `agents/flowchart_agent.py` | Feed summaries + dep graph to Groq → Mermaid TD diagram |
| Renderer | `agents/renderer_agent.py` | Write `explanation.md`, `flowchart.mmd`, `flowchart.html` |

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt
# Sentence Transformers will auto-download model weights on first run (~420MB)

# 2. Set environment variables
export GROQ_API_KEY="gsk_..."       # Groq — all LLM inference
export ENDEE_API_KEY="..."          # Endee vector DB
export ENDEE_BASE_URL="http://..."  # Optional: custom Endee host/port
# No OPENAI_API_KEY needed — embeddings run locally!
```

Get a free Groq API key at: https://console.groq.com

## Usage

```bash
python main.py https://github.com/owner/repo

# Custom output directory
python main.py https://github.com/tiangolo/fastapi --output-dir ./fastapi-analysis

# Use a different Groq model
python main.py https://github.com/owner/repo --groq-model mixtral-8x7b-32768

# Custom Endee URL
python main.py https://github.com/owner/repo --endee-url http://localhost:8081/api/v1
```

### Available Groq Models

| Model | Context | Best for |
|---|---|---|
| `llama-3.3-70b-versatile` *(default)* | 128k | Best overall quality |
| `llama3-70b-8192` | 8k | Fast, high quality |
| `mixtral-8x7b-32768` | 32k | Long-context analysis |
| `llama-3.1-8b-instant` | 128k | Fastest / cheapest |
| `gemma2-9b-it` | 8k | Lightweight alternative |

## Output Files

| File | Description |
|---|---|
| `output/explanation.md` | Full Markdown explanation of the repository |
| `output/flowchart.mmd` | Raw Mermaid diagram source |
| `output/flowchart.html` | **Self-contained interactive HTML viewer** with dark theme, zoom controls, and tab navigation |

---

## Endee Index Structure

Two indexes are created per repository:

| Index Name Pattern | Content | Dimension |
|---|---|---|
| `code_{owner}_{repo}` | Source code chunks | 768 (CodeBERT) |
| `text_{owner}_{repo}` | README / Markdown documentation chunks | 768 (all-mpnet-base-v2) |

---

## Customisation

- **Swap embedding model** — edit `TEXT_EMBEDDING_MODEL` / `CODE_EMBEDDING_MODEL` in `utils/helpers.py` (any HuggingFace ST-compatible model works; update `EMBEDDING_DIM` to match)
- **Add more languages** — extend `CODE_EXTENSIONS` in `code_analyzer.py`
- **Adjust chunk size** — edit `chunk_code()` / `chunk_text()` in `utils/helpers.py`
- **Tune Endee retrieval** — adjust `TOP_K`, `EF`, filter params in `retriever_agent.py`


---

## Architecture

```
clone_node
    │
    ├─── code_analyzer_node       → code embeddings → Endee (code index)
    ├─── text_analyzer_node       → text embeddings → Endee (text index)
    └─── dependency_analyzer_node → static import graph
             │
         retriever_node           ← queries both Endee indexes for context
             │
         synthesizer_node         → LLM writes full explanation.md
             │
         flowchart_node            → LLM generates Mermaid diagram
             │
         renderer_node             → writes output files
```

### Agents

| Agent | File | Responsibility |
|---|---|---|
| Clone | `agents/clone_agent.py` | `git clone --depth=1` the target repo |
| Code Analyzer | `agents/code_analyzer.py` | Parse source files, chunk, embed with `text-embedding-3-small`, upsert to Endee |
| Text Analyzer | `agents/text_analyzer.py` | Parse README / Markdown docs, chunk, embed, upsert to Endee |
| Dependency Analyzer | `agents/dependency_analyzer.py` | Static import graph via AST (Python) and regex (JS/TS/Go/etc.) |
| Retriever | `agents/retriever_agent.py` | Build targeted queries from summaries, search Endee, de-duplicate results |
| Synthesizer | `agents/synthesizer_agent.py` | Feed all context to GPT-4o, generate structured explanation |
| Flowchart | `agents/flowchart_agent.py` | Feed summaries + dep graph to GPT-4o, generate Mermaid TD diagram |
| Renderer | `agents/renderer_agent.py` | Write `explanation.md`, `flowchart.mmd`, `flowchart.html` |

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
export OPENAI_API_KEY="sk-..."
export ENDEE_API_KEY="..."          # Your Endee API key
export ENDEE_BASE_URL="http://..."  # Optional: custom Endee URL/port
```

## Usage

```bash
python main.py https://github.com/owner/repo

# Custom output directory
python main.py https://github.com/tiangolo/fastapi --output-dir ./fastapi-analysis

# Custom Endee URL
python main.py https://github.com/owner/repo --endee-url http://localhost:8081/api/v1

# Use a different OpenAI model
python main.py https://github.com/owner/repo --openai-model gpt-4o-mini
```

## Output Files

| File | Description |
|---|---|
| `output/explanation.md` | Full Markdown explanation of the repository |
| `output/flowchart.mmd` | Raw Mermaid diagram source |
| `output/flowchart.html` | **Self-contained interactive HTML viewer** with dark theme, zoom controls, and tab navigation |

---

## Endee Index Structure

Two indexes are created per repository:

| Index Name Pattern | Content | Dimension |
|---|---|---|
| `code_{owner}_{repo}` | Source code chunks (`.py`, `.js`, `.ts`, `.go`, …) | 1536 |
| `text_{owner}_{repo}` | README / Markdown documentation chunks | 1536 |

Each vector stores:
- `meta.file` — relative file path
- `meta.text` — first 500 chars of the chunk
- `filter.type` — `"code"` or `"text"`

---

## Customisation

- **Add more languages** — extend `CODE_EXTENSIONS` in `code_analyzer.py`
- **Adjust chunk size** — edit `chunk_code()` / `chunk_text()` in `utils/helpers.py`
- **Change embedding model** — update `get_code_embeddings()` in `utils/helpers.py`
- **Tune Endee retrieval** — adjust `TOP_K`, `EF`, filter params in `retriever_agent.py`
- **Swap LLM** — pass `--openai-model` flag or edit default in `pipeline.py`