from __future__ import annotations

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - lets non-LangGraph tests import package
    END = "__end__"  # type: ignore[assignment]
    START = "__start__"  # type: ignore[assignment]
    StateGraph = None  # type: ignore[assignment]


def require_langgraph() -> None:
    if StateGraph is None:  # pragma: no cover
        raise RuntimeError("langgraph is required to build agent workflows")
