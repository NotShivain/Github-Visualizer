"""
pipeline.py  —  LangGraph pipeline definition.

"""
from typing import Any
from langgraph.graph import StateGraph, END

from state import RepoState
from agents.clone_agent import clone_node
from agents.code_analyzer import code_analyzer_node
from agents.text_analyzer import text_analyzer_node
from agents.dependency_analyzer import dependency_analyzer_node
from agents.retriever_agent import retriever_node
from agents.synthesizer_agent import synthesizer_node
from agents.flowchart_agent import flowchart_node
from agents.renderer_agent import renderer_node


def build_pipeline(groq_model: str = "llama-3.3-70b-versatile", endee_base_url: str | None = None) -> Any:
    """Compile and return the LangGraph runnable."""

    def _make_node(fn):
        """Wrap a node so it always receives model/endee config."""
        def _wrapped(state: RepoState) -> RepoState:
            state = dict(state)
            state.setdefault("_groq_model", groq_model)
            state.setdefault("_endee_base_url", endee_base_url)
            return fn(state)
        _wrapped.__name__ = fn.__name__
        return _wrapped

    builder = StateGraph(RepoState)

    builder.add_node("clone",        _make_node(clone_node))
    builder.add_node("code",         _make_node(code_analyzer_node))
    builder.add_node("text",         _make_node(text_analyzer_node))
    builder.add_node("deps",         _make_node(dependency_analyzer_node))
    builder.add_node("retriever",    _make_node(retriever_node))
    builder.add_node("synthesizer",  _make_node(synthesizer_node))
    builder.add_node("flowchart",    _make_node(flowchart_node))
    builder.add_node("renderer",     _make_node(renderer_node))

    builder.set_entry_point("clone")

    builder.add_edge("clone", "code")
    builder.add_edge("clone", "text")
    builder.add_edge("clone", "deps")

    builder.add_edge("code",  "retriever")
    builder.add_edge("text",  "retriever")
    builder.add_edge("deps",  "retriever")

    builder.add_edge("retriever",   "synthesizer")
    builder.add_edge("synthesizer", "flowchart")
    builder.add_edge("flowchart",   "renderer")
    builder.add_edge("renderer",    END)

    return builder.compile()
