from __future__ import annotations

from uuid import uuid4
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from orchestrator_agents.agents import CodingAgent, ResearchAgent, WritingAgent
from orchestrator_agents.graph.state import OrchestratorState
from orchestrator_agents.routing import RoutingService
from orchestrator_agents.schemas import AgentTask, RouteDecision, RouteVerification
from orchestrator_agents.storage.artifact_store import JsonArtifactStore

DestinationLiteral = Literal[
    "research_agent",
    "coding_agent",
    "writing_agent",
    "clarification_node",
    "fallback_agent",
]


def build_orchestrator_graph(
    *,
    artifact_store: JsonArtifactStore | None = None,
    routing_service: RoutingService | None = None,
    checkpointer=None,
):
    """Build the orchestrator graph.

    Subagents are stateless workers. The graph thread/checkpointer owns workflow
    continuity. The artifact store owns durable large outputs.
    """

    artifact_store = artifact_store or JsonArtifactStore()
    routing_service = routing_service or RoutingService()

    research = ResearchAgent()
    coding = CodingAgent()
    writing = WritingAgent()

    def start_turn_node(state: OrchestratorState) -> dict:
        run_id = f"run_{uuid4().hex[:12]}"
        user_message = {"role": "user", "content": state["user_query"], "run_id": run_id}
        return {
            "run_id": run_id,
            "messages": [user_message],
            "route_history": [
                {
                    "stage": "start_turn",
                    "run_id": run_id,
                    "thread_id": state["thread_id"],
                    "user_query": state["user_query"],
                }
            ],
        }

    def route_node(state: OrchestratorState) -> Command[DestinationLiteral]:
        decision, verification, destination = routing_service.decide(state["user_query"])

        handoff_event = {
            "handoff_id": f"handoff_{uuid4().hex[:12]}",
            "run_id": state["run_id"],
            "thread_id": state["thread_id"],
            "from_agent": "orchestrator",
            "to_agent": destination,
            "primary_intent": decision.primary_intent,
            "confidence": decision.confidence,
            "reason": decision.reasoning_summary,
        }

        update = {
            "selected_agent": destination,
            "current_agent": destination,
            "route_decision": decision.model_dump(),
            "route_verification": verification.model_dump(),
            "handoff_history": [handoff_event],
            "route_history": [
                {
                    "stage": "route_policy",
                    "run_id": state["run_id"],
                    "target_agent": decision.target_agent,
                    "selected_agent": destination,
                    "confidence": decision.confidence,
                    "ambiguity_score": decision.ambiguity_score,
                    "verification_approved": verification.approved,
                }
            ],
        }

        if destination == "clarification_node":
            update["clarification_question"] = (
                decision.clarification_question
                or "Can you clarify whether this is research, coding, or writing?"
            )

        return Command(update=update, goto=destination)

    def _build_task(state: OrchestratorState, target_agent: str) -> AgentTask:
        return AgentTask(
            task_id=f"task_{uuid4().hex[:12]}",
            target_agent=target_agent,  # type: ignore[arg-type]
            user_query=state["user_query"],
            instruction=state["user_query"],
            context={
                "user_id": state["user_id"],
                "thread_id": state["thread_id"],
                "run_id": state["run_id"],
                # Pass references, not huge blobs. Agents can retrieve artifacts if needed.
                "available_artifact_ids": state.get("artifact_ids", []),
                "route_decision": state.get("route_decision", {}),
            },
        )

    def research_agent_node(state: OrchestratorState) -> dict:
        result = research.invoke(_build_task(state, "research_agent"), artifact_store)
        return _agent_result_update(result)

    def coding_agent_node(state: OrchestratorState) -> dict:
        result = coding.invoke(_build_task(state, "coding_agent"), artifact_store)
        return _agent_result_update(result)

    def writing_agent_node(state: OrchestratorState) -> dict:
        result = writing.invoke(_build_task(state, "writing_agent"), artifact_store)
        return _agent_result_update(result)

    def _agent_result_update(result) -> dict:
        return {
            "agent_result": result.result,
            "artifact_ids": result.artifact_ids,
            "messages": [
                {
                    "role": "assistant",
                    "name": result.agent_name,
                    "content": result.result,
                    "task_id": result.task_id,
                }
            ],
            "route_history": [
                {
                    "stage": "subagent_completed",
                    "agent_name": result.agent_name,
                    "task_id": result.task_id,
                    "confidence": result.confidence,
                    "artifact_ids": result.artifact_ids,
                }
            ],
        }

    def clarification_node(state: OrchestratorState) -> dict:
        question = state.get(
            "clarification_question",
            "Can you clarify whether you want research, coding, or writing help?",
        )
        return {
            "final_answer": question,
            "messages": [{"role": "assistant", "name": "orchestrator", "content": question}],
        }

    def fallback_agent_node(state: OrchestratorState) -> dict:
        answer = (
            "I could not confidently route this request to research, coding, or writing. "
            "Please clarify the goal or add more task details."
        )
        return {
            "agent_result": answer,
            "messages": [{"role": "assistant", "name": "fallback_agent", "content": answer}],
        }

    def finalizer_node(state: OrchestratorState) -> dict:
        if state.get("final_answer"):
            return {}

        selected = state.get("selected_agent", "unknown")
        result = state.get("agent_result", "No result was produced.")
        final = f"Handled by `{selected}`.\n\n{result}"
        return {
            "final_answer": final,
            "messages": [{"role": "assistant", "name": "finalizer", "content": final}],
        }

    builder = StateGraph(OrchestratorState)
    builder.add_node("start_turn", start_turn_node)
    builder.add_node("route", route_node)
    builder.add_node("research_agent", research_agent_node)
    builder.add_node("coding_agent", coding_agent_node)
    builder.add_node("writing_agent", writing_agent_node)
    builder.add_node("clarification_node", clarification_node)
    builder.add_node("fallback_agent", fallback_agent_node)
    builder.add_node("finalizer", finalizer_node)

    builder.add_edge(START, "start_turn")
    builder.add_edge("start_turn", "route")

    for agent in ["research_agent", "coding_agent", "writing_agent", "fallback_agent"]:
        builder.add_edge(agent, "finalizer")

    builder.add_edge("clarification_node", END)
    builder.add_edge("finalizer", END)

    return builder.compile(checkpointer=checkpointer) if checkpointer else builder.compile()
