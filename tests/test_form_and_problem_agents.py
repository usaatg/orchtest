from __future__ import annotations

from orchestrator_agents.agents import DEFAULT_PROBLEM_FORM_SCHEMA, ProblemStatementAgent, SmartFormBuilderAgent
from orchestrator_agents.dependencies import invalidate_dependents
from orchestrator_agents.schemas import FormAgentInput, ProblemStatementInput
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


def test_smart_form_agent_direct_multiturn():
    agent = SmartFormBuilderAgent()
    state = None
    out = agent.run(FormAgentInput(user_message="I want to define a problem", form_schema=DEFAULT_PROBLEM_FORM_SCHEMA, form_state=state))
    assert out.status == "in_progress"
    assert "primary stakeholder" in out.assistant_message
    state = out.updated_form_state

    for msg in ["Plant managers", "Manual reporting is slow", "Automated KPI summaries", "Delayed decisions"]:
        out = agent.run(FormAgentInput(user_message=msg, form_schema=DEFAULT_PROBLEM_FORM_SCHEMA, form_state=state))
        state = out.updated_form_state
    assert out.status == "ready_for_review"

    out = agent.run(FormAgentInput(user_message="yes", form_schema=DEFAULT_PROBLEM_FORM_SCHEMA, form_state=state))
    assert out.completed is True
    assert out.artifact_payload is not None
    assert out.artifact_payload["fields"]["stakeholder"] == "Plant managers"


def test_problem_statement_agent_direct_from_form_data():
    agent = ProblemStatementAgent()
    output = agent.run(
        ProblemStatementInput(
            form_artifact_id="form_1",
            form_artifact_version=1,
            form_content={
                "fields": {
                    "stakeholder": "Plant managers",
                    "current_pain": "manual reporting is slow",
                    "desired_outcome": "automated KPI summaries",
                    "business_impact": "faster decisions",
                }
            },
        )
    )
    assert "Plant managers" in output.problem_statement
    assert output.depends_on[0].artifact_id == "form_1"


def test_dependency_invalidation_marks_problem_statement_stale(tmp_path):
    store = JsonArtifactStore(tmp_path)
    user_id = "u1"
    thread_id = "t1"
    form_v1 = store.put(
        user_id=user_id,
        namespace=("threads", thread_id, "artifacts"),
        artifact_type="smart_form",
        content="{'fields': {'stakeholder': 'Operations managers'}}",
        summary="form v1",
        source_thread_id=thread_id,
        created_by="smart_form_builder_agent",
    )
    problem_agent = ProblemStatementAgent()
    result = problem_agent.invoke(
        task=__import__("orchestrator_agents.schemas", fromlist=["AgentTask"]).AgentTask(
            task_id="ps1",
            target_agent="problem_statement_agent",
            user_query="Create problem statement",
            instruction="Create problem statement",
            context={"user_id": user_id, "thread_id": thread_id, "latest_form_artifact_id": form_v1},
        ),
        artifact_store=store,
    )
    ps_id = result.artifact_ids[0]
    form_v2 = store.put(
        user_id=user_id,
        namespace=("threads", thread_id, "artifacts"),
        artifact_type="smart_form",
        content="{'fields': {'stakeholder': 'Plant managers'}}",
        summary="form v2",
        source_thread_id=thread_id,
        created_by="smart_form_builder_agent",
        supersedes=form_v1,
    )
    stale_ids, events = invalidate_dependents(artifact_store=store, user_id=user_id, old_artifact_id=form_v1, new_artifact_id=form_v2)
    assert ps_id in stale_ids
    assert events[0]["event_type"] == "artifact_invalidated"
    assert store.get_any_for_user(user_id=user_id, artifact_id=ps_id).status == "stale"
