"""
GitHub Repository Visualizer
Multi-agent system using LangGraph + Endee vector database
LLMs powered by Groq  |  Embeddings via sentence transformer
"""
import os
import sys
import argparse
from pipeline import build_pipeline
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Repository Visualizer — LangGraph + Groq + Endee"
    )
    parser.add_argument(
        "repo_url",
        help="GitHub repository URL (e.g. https://github.com/owner/repo)",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Directory to write the explanation and flowchart (default: ./output)",
    )
    parser.add_argument(
        "--groq-model",
        default="llama-3.3-70b-versatile",
        help=(
            "Groq model for LLM nodes (default: llama-3.3-70b-versatile). "
            "Other options: llama3-70b-8192, mixtral-8x7b-32768, gemma2-9b-it, "
            "llama-3.1-8b-instant"
        ),
    )
    parser.add_argument(
        "--endee-url",
        default=None,
        help="Custom Endee base URL (default: uses ENDEE_BASE_URL env var or SDK default)",
    )
    args = parser.parse_args()

    # ── Validate environment ────────────────────────────────────────────────
    if not os.getenv("GROQ_API_KEY"):
        sys.exit("ERROR: GROQ_API_KEY environment variable is not set.")

    os.makedirs(args.output_dir, exist_ok=True)

    # ── Build and run the pipeline ──────────────────────────────────────────
    graph = build_pipeline(
        groq_model=args.groq_model,
        endee_base_url=args.endee_url or os.getenv("ENDEE_BASE_URL"),
    )

    initial_state = {
        "repo_url": args.repo_url,
        "output_dir": args.output_dir,
    }

    print(f"\n🔍  Analysing repository: {args.repo_url}")
    print(f"🤖  LLM     : Groq / {args.groq_model}")
    print(f"🔢  Embeddings: Sentence Transformers (local)")
    print("─" * 60)

    final_state = graph.invoke(initial_state)

    print("\n✅  Done!")
    print(f"   Explanation : {final_state['explanation_path']}")
    print(f"   Flowchart   : {final_state['flowchart_path']}")
    print(f"   Mermaid src : {final_state['mermaid_path']}")


if __name__ == "__main__":
    main()
