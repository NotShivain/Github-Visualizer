"""
agents/renderer_agent.py
Node: renderer_node

Writes all artefacts to the output directory:
  - explanation.md      — Markdown explanation of the repository
  - flowchart.mmd       — Raw Mermaid diagram source
  - flowchart.html      — Self-contained HTML page with interactive Mermaid viewer

Populates state:
  - explanation_path
  - mermaid_path
  - flowchart_path
"""
from __future__ import annotations
import os
from pathlib import Path

from state import RepoState

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GitHub Visualizer — ___REPO_NAME___</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg:      #0a0e1a;
      --surface: #111827;
      --border:  #1e2d45;
      --accent:  #00d4ff;
      --accent2: #7c3aed;
      --text:    #e2e8f0;
      --muted:   #64748b;
      --glow:    0 0 20px rgba(0, 212, 255, 0.15);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Syne', sans-serif;
      min-height: 100vh;
      overflow-x: hidden;
    }}
    /* ── Animated grid background ── */
    body::before {{
      content: '';
      position: fixed; inset: 0;
      background-image:
        linear-gradient(rgba(0,212,255,.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,212,255,.04) 1px, transparent 1px);
      background-size: 40px 40px;
      pointer-events: none;
      z-index: 0;
    }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem;
      position: relative;
      z-index: 1;
    }}
    /* ── Header ── */
    header {{
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 2rem 0 3rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 3rem;
    }}
    .logo {{
      width: 44px; height: 44px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1.4rem;
      box-shadow: var(--glow);
    }}
    h1 {{
      font-size: clamp(1.4rem, 3vw, 2rem);
      font-weight: 800;
      letter-spacing: -0.02em;
    }}
    h1 span {{
      color: var(--accent);
    }}
    .badge {{
      margin-left: auto;
      background: rgba(0,212,255,0.1);
      border: 1px solid rgba(0,212,255,0.3);
      color: var(--accent);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      padding: 0.3rem 0.8rem;
      border-radius: 99px;
    }}
    /* ── Tab navigation ── */
    .tabs {{
      display: flex;
      gap: 0.25rem;
      margin-bottom: 2rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 0.25rem;
      width: fit-content;
    }}
    .tab {{
      padding: 0.6rem 1.4rem;
      border: none;
      background: transparent;
      color: var(--muted);
      font-family: 'Syne', sans-serif;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      border-radius: 8px;
      transition: all 0.2s;
    }}
    .tab.active {{
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #fff;
      box-shadow: var(--glow);
    }}
    .tab:not(.active):hover {{ color: var(--text); background: rgba(255,255,255,0.05); }}
    /* ── Panels ── */
    .panel {{ display: none; }}
    .panel.active {{ display: block; }}
    /* ── Flowchart panel ── */
    .chart-wrapper {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 2rem;
      overflow: auto;
      box-shadow: var(--glow);
      min-height: 400px;
    }}
    .mermaid {{
      display: flex;
      justify-content: center;
    }}
    /* Override Mermaid colours */
    .mermaid svg {{
      max-width: 100%;
      height: auto;
    }}
    /* ── Explanation panel ── */
    .explanation {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 2.5rem;
      line-height: 1.8;
      font-family: 'Syne', sans-serif;
    }}
    .explanation h1, .explanation h2, .explanation h3 {{
      color: var(--accent);
      margin: 2rem 0 0.8rem;
      font-weight: 700;
    }}
    .explanation h1 {{ font-size: 1.6rem; }}
    .explanation h2 {{ font-size: 1.25rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; }}
    .explanation h3 {{ font-size: 1.05rem; color: #a5f3fc; }}
    .explanation p {{ margin-bottom: 1rem; color: #cbd5e1; }}
    .explanation code {{
      font-family: 'JetBrains Mono', monospace;
      background: rgba(0,212,255,0.08);
      border: 1px solid rgba(0,212,255,0.15);
      padding: 0.15em 0.45em;
      border-radius: 4px;
      font-size: 0.88em;
      color: var(--accent);
    }}
    .explanation pre {{
      background: #060d1a;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.2rem;
      overflow-x: auto;
      margin: 1rem 0;
    }}
    .explanation pre code {{
      background: none;
      border: none;
      padding: 0;
      color: #a5f3fc;
      font-size: 0.85rem;
    }}
    .explanation ul, .explanation ol {{
      padding-left: 1.5rem;
      margin-bottom: 1rem;
    }}
    .explanation li {{ color: #cbd5e1; margin-bottom: 0.3rem; }}
    .explanation strong {{ color: var(--text); }}
    /* ── Source panel ── */
    .source-code {{
      background: #060d1a;
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 2rem;
      overflow-x: auto;
    }}
    .source-code pre {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      color: #a5f3fc;
      line-height: 1.7;
      white-space: pre;
    }}
    /* ── Zoom controls ── */
    .controls {{
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1rem;
      align-items: center;
    }}
    .btn {{
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      padding: 0.4rem 0.9rem;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .zoom-level {{
      color: var(--muted);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      min-width: 50px;
      text-align: center;
    }}
    footer {{
      text-align: center;
      padding: 3rem 0 1.5rem;
      color: var(--muted);
      font-size: 0.8rem;
      font-family: 'JetBrains Mono', monospace;
      border-top: 1px solid var(--border);
      margin-top: 4rem;
    }}
    footer a {{ color: var(--accent); text-decoration: none; }}
  </style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">⬡</div>
    <div>
      <h1>GitHub <span>Visualizer</span></h1>
      <div style="color:var(--muted);font-size:0.85rem;margin-top:0.2rem;font-family:'JetBrains Mono',monospace">___REPO_NAME___</div>
    </div>
    <div class="badge">LangGraph · Endee</div>
  </header>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('flow', this)">⬡ Flowchart</button>
    <button class="tab" onclick="switchTab('explain', this)">📄 Explanation</button>
    <button class="tab" onclick="switchTab('src', this)">{'</>'} Mermaid Source</button>
  </div>

  <!-- Flowchart panel -->
  <div id="panel-flow" class="panel active">
    <div class="controls">
      <button class="btn" onclick="zoom(-0.2)">−</button>
      <span class="zoom-level" id="zoom-label">100%</span>
      <button class="btn" onclick="zoom(0.2)">+</button>
      <button class="btn" onclick="resetZoom()">↺ Reset</button>
    </div>
    <div class="chart-wrapper">
      <div class="mermaid" id="chart-inner">
___MERMAID_ESCAPED___
      </div>
    </div>
  </div>

  <!-- Explanation panel -->
  <div id="panel-explain" class="panel">
    <div class="explanation" id="explanation-content">
      <!-- Rendered by marked.js -->
    </div>
  </div>

  <!-- Mermaid source panel -->
  <div id="panel-src" class="panel">
    <div class="source-code">
      <pre id="mermaid-source"></pre>
    </div>
  </div>

  <footer>
    Generated by <a href="#">GitHub Visualizer</a> · Powered by LangGraph + Endee
  </footer>
</div>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
  // ── Data ──────────────────────────────────────────────────────────────────
  const EXPLANATION_MD = ___EXPLANATION_JSON___;
  const MERMAID_SRC    = ___MERMAID_JSON___;

  // ── Mermaid init ──────────────────────────────────────────────────────────
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'dark',
    themeVariables: {{
      primaryColor:       '#1e2d45',
      primaryTextColor:   '#e2e8f0',
      primaryBorderColor: '#00d4ff',
      lineColor:          '#00d4ff',
      secondaryColor:     '#111827',
      tertiaryColor:      '#0a0e1a',
      edgeLabelBackground:'#111827',
      clusterBkg:         '#111827',
      titleColor:         '#00d4ff',
    }},
    flowchart: {{ curve: 'basis', htmlLabels: true }},
    securityLevel: 'loose',
  }});

  // ── Tab switching ─────────────────────────────────────────────────────────
  function switchTab(name, btn) {{
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-' + name).classList.add('active');
    btn.classList.add('active');

    if (name === 'explain') {{
      document.getElementById('explanation-content').innerHTML = marked.parse(EXPLANATION_MD);
    }}
    if (name === 'src') {{
      document.getElementById('mermaid-source').textContent = MERMAID_SRC;
    }}
  }}

  // ── Zoom ──────────────────────────────────────────────────────────────────
  let scale = 1;
  function zoom(delta) {{
    scale = Math.max(0.3, Math.min(3, scale + delta));
    document.getElementById('chart-inner').style.transform = `scale(${{scale}})`;
    document.getElementById('chart-inner').style.transformOrigin = 'top center';
    document.getElementById('zoom-label').textContent = Math.round(scale * 100) + '%';
  }}
  function resetZoom() {{
    scale = 1;
    document.getElementById('chart-inner').style.transform = 'scale(1)';
    document.getElementById('zoom-label').textContent = '100%';
  }}
</script>
</body>
</html>
"""


def renderer_node(state: RepoState) -> RepoState:
    import json

    output_dir:  str = state.get("output_dir", "./output")
    repo_name:   str = state.get("repo_name", "unknown/repo")
    explanation: str = state.get("explanation", "")
    mermaid_code:str = state.get("mermaid_code", "flowchart TD\n  A[No diagram generated]")

    os.makedirs(output_dir, exist_ok=True)

    # ── 1. explanation.md ────────────────────────────────────────────────────
    md_path = os.path.join(output_dir, "explanation.md")
    Path(md_path).write_text(
        f"# {repo_name} — Repository Explanation\n\n{explanation}\n",
        encoding="utf-8",
    )

    # ── 2. flowchart.mmd ────────────────────────────────────────────────────
    mmd_path = os.path.join(output_dir, "flowchart.mmd")
    Path(mmd_path).write_text(mermaid_code, encoding="utf-8")

    # ── 3. flowchart.html ───────────────────────────────────────────────────
    # Escape mermaid for embedding inside <div class="mermaid">
    mermaid_escaped = mermaid_code.replace("</", "<\\/")

    html = (
        HTML_TEMPLATE
        .replace("___REPO_NAME___",       repo_name)
        .replace("___MERMAID_ESCAPED___", mermaid_escaped)
        .replace("___EXPLANATION_JSON___",json.dumps(explanation))
        .replace("___MERMAID_JSON___",    json.dumps(mermaid_code))
    )

    html_path = os.path.join(output_dir, "flowchart.html")
    Path(html_path).write_text(html, encoding="utf-8")

    print(f"  [render] Wrote explanation.md, flowchart.mmd, flowchart.html → {output_dir}/")

    return {
        "explanation_path": md_path,
        "mermaid_path":     mmd_path,
        "flowchart_path":   html_path,
    }