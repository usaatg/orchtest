from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from router_subagents.state import BestInsightsState, SmartFormState


def _last_human_text(messages: list | None) -> str:
    if not messages:
        return ""

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)

        # Allows dict-shaped messages in tests or callers.
        if isinstance(message, dict) and message.get("role") in {"human", "user"}:
            return str(message.get("content", ""))

    return ""


def build_smart_form_builder_graph(checkpointer: InMemorySaver):
    """
    Build an independently compiled subagent graph.

    This toy subagent accumulates form fields across calls in its own thread.
    """
    builder = StateGraph(SmartFormState)

    def extract_fields(state: SmartFormState) -> SmartFormState:
        text = _last_human_text(state.get("messages"))
        existing = list(state.get("form_fields", []))
        call_count = int(state.get("call_count", 0)) + 1

        candidate_fields: list[str] = []
        lowered = text.lower()

        if "customer" in lowered or "user" in lowered:
            candidate_fields.append("customer_name")
        if "email" in lowered:
            candidate_fields.append("email")
        if "budget" in lowered:
            candidate_fields.append("budget")
        if "deadline" in lowered or "date" in lowered:
            candidate_fields.append("deadline")
        if not candidate_fields:
            candidate_fields.append("free_text_request")

        merged_fields = existing[:]
        for field in candidate_fields:
            if field not in merged_fields:
                merged_fields.append(field)

        response = (
            "Smart Form Builder updated the form. "
            f"Fields now: {', '.join(merged_fields)}. "
            f"Subagent call count: {call_count}."
        )

        return {
            "form_fields": merged_fields,
            "call_count": call_count,
            "messages": [AIMessage(content=response)],
        }

    builder.add_node("extract_fields", extract_fields)
    builder.add_edge(START, "extract_fields")
    builder.add_edge("extract_fields", END)

    return builder.compile(checkpointer=checkpointer)


def build_best_insights_graph(checkpointer: InMemorySaver):
    """
    Build an independently compiled subagent graph.

    This toy subagent accumulates insights across calls in its own thread.
    """
    builder = StateGraph(BestInsightsState)

    def generate_insights(state: BestInsightsState) -> BestInsightsState:
        text = _last_human_text(state.get("messages"))
        existing = list(state.get("insights", []))
        call_count = int(state.get("call_count", 0)) + 1

        lowered = text.lower()
        if "form" in lowered:
            insight = "The form should capture only fields needed for downstream decisions."
        elif "concept" in lowered or "idea" in lowered:
            insight = "Concepts should be evaluated against user value, feasibility, and differentiation."
        elif "workflow" in lowered or "agent" in lowered:
            insight = "Agent workflows should make dependencies explicit and preserve each agent's state boundary."
        else:
            insight = "The next best insight depends on the user's current goal and missing context."

        if insight not in existing:
            existing.append(insight)

        response = (
            "Best Insights generated an insight. "
            f"Insights stored: {len(existing)}. "
            f"Subagent call count: {call_count}."
        )

        return {
            "insights": existing,
            "call_count": call_count,
            "messages": [AIMessage(content=response)],
        }

    builder.add_node("generate_insights", generate_insights)
    builder.add_edge(START, "generate_insights")
    builder.add_edge("generate_insights", END)

    return builder.compile(checkpointer=checkpointer)
