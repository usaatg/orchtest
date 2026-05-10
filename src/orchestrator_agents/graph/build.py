from __future__ import annotations

from uuid import uuid4
from typing import Literal

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command
except Exception:  # pragma: no cover - lets non-LangGraph tests import package
    END = "__end__"  # type: ignore[assignment]
    START = "__start__"  # type: ignore[assignment]
    StateGraph = None  # type: ignore[assignment]

    class Command(dict):  # type: ignore[no-redef]
        def __init__(self, update=None, goto=None):
            super().__init__(update=update or {}, goto=goto)
            self.update = update or {}
            self.goto = goto

from orchestrator_agents.agents import CodingAgent, ProblemStatementAgent, ResearchAgent, SmartFormBuilderAgent, WritingAgent
from orchestrator_agents.graph.context import build_agent_task
from orchestrator_agents.graph.state import OrchestratorState
from orchestrator_agents.observability import make_event
from orchestrator_agents.routing import RoutingService
from orchestrator_agents.schemas import HandoffEvent, ImportedContext, RoutePlan, RouteVerification
from orchestrator_agents.storage.artifact_store import JsonArtifactStore

DestinationLiteral = Literal[
    "research_agent",
    "coding_agent",
    "writing_agent",
    "smart_form_builder_agent",
    "problem_statement_agent",
    "clarification_node",
    "fallback_agent",
    "finalizer",
]


def build_orchestrator_graph(*, checkpointer=None, artifact_store: JsonArtifactStore | None = None):
    """Build the orchestrator graph.

    Runtime handoffs use Command(goto=...). Some visual graph renderers may not show these
    dynamic edges as static arrows; see README for details.
    """

    if StateGraph is None:  # pragma: no cover
        raise RuntimeError("langgraph is required to build the graph")

    artifact_store = artifact_store or JsonArtifactStore()
    routing_service = RoutingService()
    agents = {
        "research_agent": ResearchAgent(),
        "coding_agent": CodingAgent(),
        "writing_agent": WritingAgent(),
        "smart_form_builder_agent": SmartFormBuilderAgent(),
        "problem_statement_agent": ProblemStatementAgent(),
    }

    def initialize_node(state: OrchestratorState) -> dict:
        run_id = state.get("run_id") or f"run_{uuid4().hex[:12]}"
        query = state["user_query"].strip()
        return {
            "run_id": run_id,
            "normalized_query": query,
            "current_route_step_index": 0,
            # Reset turn-scoped terminal output so checkpointed multi-turn sessions
            # do not keep returning a prior turn's final_answer.
            "final_answer": "",
            "route_history": [
                {"stage": "normalize_request", "normalized_query": query, "run_id": run_id}
            ],
            "observability_events": [
                make_event(
                    event_type="request_normalized",
                    thread_id=state["thread_id"],
                    run_id=run_id,
                    payload={"query_length": len(query)},
                )
            ],
        }

    def import_context_node(state: OrchestratorState) -> dict:
        imported: list[dict] = []
        user_id = state["user_id"]

        for artifact_id in state.get("referenced_artifact_ids", []):
            record = artifact_store.get_any_for_user(user_id=user_id, artifact_id=artifact_id)
            if record:
                imported.append(
                    ImportedContext(
                        source_thread_id=record.source_thread_id,
                        source_artifact_id=record.artifact_id,
                        # Import curated summaries into graph state, not full artifact content.
                        # Downstream agents can load full content by artifact ID if needed.
                        content=record.summary,
                        summary=record.summary,
                        metadata={**record.metadata, "artifact_type": record.artifact_type, "full_content_in_store": True},
                    ).model_dump()
                )

        # Thread references are read-only. We import summaries from that thread's artifacts.
        for source_thread_id in state.get("referenced_thread_ids", []):
            for record in artifact_store.list_for_thread(user_id=user_id, thread_id=source_thread_id):
                imported.append(
                    ImportedContext(
                        source_thread_id=source_thread_id,
                        source_artifact_id=record.artifact_id,
                        # Import curated summaries into graph state, not full artifact content.
                        # Downstream agents can load full content by artifact ID if needed.
                        content=record.summary,
                        summary=record.summary,
                        metadata={**record.metadata, "artifact_type": record.artifact_type, "full_content_in_store": True},
                    ).model_dump()
                )

        return {
            "imported_context": imported,
            "observability_events": [
                make_event(
                    event_type="context_imported",
                    thread_id=state["thread_id"],
                    run_id=state["run_id"],
                    payload={"count": len(imported)},
                )
            ],
        }

    def route_node(state: OrchestratorState) -> dict:
        plan, verification, destination, policy_reason = routing_service.decide_plan(
            state["normalized_query"], state=state
        )
        return {
            "route_plan": plan.model_dump(),
            "route_verification": verification.model_dump(),
            "selected_agent": destination,
            "route_policy_reason": policy_reason,
            "route_history": [
                {
                    "stage": "route_policy_gate",
                    "mode": plan.mode,
                    "selected_agent": destination,
                    "confidence": plan.confidence,
                    "ambiguity_score": plan.ambiguity_score,
                    "reason": policy_reason,
                }
            ],
            "observability_events": [
                make_event(
                    event_type="route_selected",
                    thread_id=state["thread_id"],
                    run_id=state["run_id"],
                    agent_id=destination,
                    payload={
                        "mode": plan.mode,
                        "confidence": plan.confidence,
                        "policy_reason": policy_reason,
                        "verification": verification.model_dump(),
                    },
                )
            ],
        }

    def route_policy_node(state: OrchestratorState) -> Command[DestinationLiteral]:
        selected = state["selected_agent"]
        plan = RoutePlan.model_validate(state["route_plan"])
        verification = RouteVerification.model_validate(state["route_verification"])

        if selected in {"clarification_node", "fallback_agent"}:
            return Command(update={"current_agent": selected}, goto=selected)

        handoff_id = f"handoff_{uuid4().hex[:12]}"
        first_step = plan.steps[0]
        event = HandoffEvent(
            handoff_id=handoff_id,
            thread_id=state["thread_id"],
            run_id=state["run_id"],
            from_agent="orchestrator",
            to_agent=selected,  # type: ignore[arg-type]
            task_id=first_step.step_id,
            confidence=plan.confidence,
            reason=state.get("route_policy_reason") or verification.reason,
        )
        return Command(
            update={
                "current_agent": selected,
                "current_route_step_index": 0,
                "handoff_history": [event.model_dump()],
                "observability_events": [
                    make_event(
                        event_type="handoff_created",
                        thread_id=state["thread_id"],
                        run_id=state["run_id"],
                        agent_id=selected,
                        task_id=first_step.step_id,
                        handoff_id=handoff_id,
                        payload={"from_agent": "orchestrator", "to_agent": selected},
                    )
                ],
            },
            goto=selected,
        )

    def make_agent_node(agent_name: str):
        def _agent_node(state: OrchestratorState) -> dict:
            task = build_agent_task(agent_name, state)
            result = agents[agent_name].invoke(task, artifact_store)
            updates = {
                "latest_agent_result": result.model_dump(),
                "agent_results": [result.model_dump()],
                "artifact_ids": result.artifact_ids,
                "messages": [
                    {
                        "role": "assistant",
                        "name": agent_name,
                        "content": result.result_summary,
                    }
                ],
                "observability_events": [
                    make_event(
                        event_type="subagent_completed",
                        thread_id=state["thread_id"],
                        run_id=state["run_id"],
                        agent_id=agent_name,
                        task_id=task.task_id,
                        payload={
                            "confidence": result.confidence,
                            "artifact_ids": result.artifact_ids,
                            "used_context_keys": result.metadata.get("used_context_keys", []),
                        },
                    )
                ],
            }
            if agent_name == "smart_form_builder_agent":
                form_state = result.metadata.get("form_state")
                if form_state:
                    updates["active_form_state"] = form_state
                    if form_state.get("status") in {"in_progress", "ready_for_review"}:
                        updates["active_workflow"] = "form_fill"
                        updates["final_answer"] = result.result
                    elif form_state.get("status") in {"completed", "cancelled"}:
                        updates["active_workflow"] = None
                if result.metadata.get("latest_form_artifact_id"):
                    updates["latest_form_artifact_id"] = result.metadata["latest_form_artifact_id"]
                stale_ids = result.metadata.get("stale_artifact_ids", [])
                dependency_events = result.metadata.get("dependency_events", [])
                if stale_ids:
                    updates["stale_artifact_ids"] = stale_ids
                    updates["dependency_events"] = dependency_events
                    updates["active_workflow"] = "dependency_resolution"
                    updates["pending_dependency_action"] = {
                        "type": "offer_regenerate_problem_statement",
                        "stale_artifact_ids": stale_ids,
                        "reason": "Form artifact changed; dependent problem statement may be stale.",
                    }
                    updates["final_answer"] = (
                        "I updated the form. Your current problem statement was generated from the previous "
                        "form version, so it may no longer be accurate. Would you like me to update the problem statement too?"
                    )
            if agent_name == "problem_statement_agent":
                latest_id = result.metadata.get("latest_problem_statement_artifact_id")
                if latest_id:
                    updates["latest_problem_statement_artifact_id"] = latest_id
                updates["active_workflow"] = None
                updates["pending_dependency_action"] = None
                updates["final_answer"] = result.result
            return updates

        return _agent_node

    def next_step_node(state: OrchestratorState) -> Command[DestinationLiteral]:
        plan = RoutePlan.model_validate(state["route_plan"])
        current_index = state.get("current_route_step_index", 0)
        next_index = current_index + 1

        if plan.mode != "multi_agent" or next_index >= len(plan.steps):
            return Command(update={"current_agent": "finalizer"}, goto="finalizer")

        next_step = plan.steps[next_index]
        selected = next_step.agent
        handoff_id = f"handoff_{uuid4().hex[:12]}"
        event = HandoffEvent(
            handoff_id=handoff_id,
            thread_id=state["thread_id"],
            run_id=state["run_id"],
            from_agent=state.get("current_agent", "orchestrator"),
            to_agent=selected,
            task_id=next_step.step_id,
            confidence=plan.confidence,
            reason="Sequential route-plan step.",
        )
        return Command(
            update={
                "selected_agent": selected,
                "current_agent": selected,
                "current_route_step_index": next_index,
                "handoff_history": [event.model_dump()],
                "observability_events": [
                    make_event(
                        event_type="handoff_created",
                        thread_id=state["thread_id"],
                        run_id=state["run_id"],
                        agent_id=selected,
                        task_id=next_step.step_id,
                        handoff_id=handoff_id,
                        payload={"route_step_index": next_index},
                    )
                ],
            },
            goto=selected,
        )

    def clarification_node(state: OrchestratorState) -> dict:
        plan = RoutePlan.model_validate(state["route_plan"])
        answer = plan.clarification_question or "Can you clarify what kind of help you want?"
        return {
            "final_answer": answer,
            "messages": [{"role": "assistant", "name": "clarification_node", "content": answer}],
        }

    def fallback_agent(state: OrchestratorState) -> dict:
        answer = (
            "I can handle this as a general request, but no specialist subagent was selected. "
            f"Policy reason: {state.get('route_policy_reason', 'No specialist route matched.')}"
        )
        return {
            "final_answer": answer,
            "latest_agent_result": {"agent_name": "fallback_agent", "result_summary": answer},
            "agent_results": [
                {
                    "task_id": "fallback",
                    "agent_name": "fallback_agent",
                    "result": answer,
                    "result_summary": answer,
                    "confidence": 0.5,
                    "artifact_ids": [],
                    "needs_followup": False,
                    "metadata": {},
                }
            ],
            "messages": [{"role": "assistant", "name": "fallback_agent", "content": answer}],
        }

    def finalizer_node(state: OrchestratorState) -> dict:
        if state.get("final_answer"):
            return {}
        results = state.get("agent_results", [])
        if not results:
            answer = "No specialist result was produced."
        else:
            parts = [r.get("result", r.get("result_summary", "")) for r in results[-3:]]
            answer = "\n\n".join(parts)
        return {
            "final_answer": answer,
            "messages": [{"role": "assistant", "name": "finalizer", "content": answer}],
        }

    builder = StateGraph(OrchestratorState)
    builder.add_node("initialize", initialize_node)
    builder.add_node("import_context", import_context_node)
    builder.add_node("route", route_node)
    builder.add_node("route_policy", route_policy_node)
    builder.add_node("research_agent", make_agent_node("research_agent"))
    builder.add_node("coding_agent", make_agent_node("coding_agent"))
    builder.add_node("writing_agent", make_agent_node("writing_agent"))
    builder.add_node("smart_form_builder_agent", make_agent_node("smart_form_builder_agent"))
    builder.add_node("problem_statement_agent", make_agent_node("problem_statement_agent"))
    builder.add_node("next_step", next_step_node)
    builder.add_node("clarification_node", clarification_node)
    builder.add_node("fallback_agent", fallback_agent)
    builder.add_node("finalizer", finalizer_node)

    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "import_context")
    builder.add_edge("import_context", "route")
    builder.add_edge("route", "route_policy")

    builder.add_edge("research_agent", "next_step")
    builder.add_edge("coding_agent", "next_step")
    builder.add_edge("writing_agent", "next_step")
    builder.add_edge("smart_form_builder_agent", "next_step")
    builder.add_edge("problem_statement_agent", "next_step")
    builder.add_edge("fallback_agent", "finalizer")
    builder.add_edge("clarification_node", END)
    builder.add_edge("finalizer", END)

    return builder.compile(checkpointer=checkpointer)
