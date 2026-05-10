from orchestrator_agents.graph.context import build_agent_task
from orchestrator_agents.schemas import RoutePlan, RouteStep


def test_context_packaging_does_not_pass_full_state():
    plan = RoutePlan(
        mode="single_agent",
        steps=[RouteStep(step_id="s1", agent="coding_agent", task="Write code", output_key="code")],
        confidence=0.9,
        ambiguity_score=0.1,
        requires_clarification=False,
        reasoning_summary="test",
    )
    state = {
        "user_query": "Build code",
        "user_id": "u1",
        "thread_id": "t1",
        "run_id": "r1",
        "route_plan": plan.model_dump(),
        "current_route_step_index": 0,
        "artifact_ids": ["artifact_1"],
        "imported_context": [],
        "secret_full_state_field": "should-not-pass",
    }
    task = build_agent_task("coding_agent", state)  # type: ignore[arg-type]
    assert task.task_id == "s1"
    assert task.context["framework"] == "LangGraph"
    assert task.context["available_artifact_ids"] == ["artifact_1"]
    assert "secret_full_state_field" not in task.context
