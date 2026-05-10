from orchestrator_agents.routing import RoutingService


def test_problem_statement_without_form_routes_to_smart_form():
    plan, _verification, destination, _reason = RoutingService().decide_plan(
        "I want to define a business problem statement",
        state={"user_query": "I want to define a business problem statement"},
    )
    assert destination == "smart_form_builder_agent"
    assert plan.steps[0].agent == "smart_form_builder_agent"


def test_problem_statement_with_form_routes_to_problem_agent():
    plan, _verification, destination, _reason = RoutingService().decide_plan(
        "Create the problem statement from my form",
        state={"user_query": "Create the problem statement from my form", "latest_form_artifact_id": "artifact_form_1"},
    )
    assert destination == "problem_statement_agent"
    assert plan.steps[0].agent == "problem_statement_agent"


def test_sticky_dependency_resolution_yes_routes_to_problem_agent():
    plan, _verification, destination, _reason = RoutingService().decide_plan(
        "yes",
        state={
            "user_query": "yes",
            "latest_form_artifact_id": "artifact_form_2",
            "active_workflow": "dependency_resolution",
            "pending_dependency_action": {"type": "offer_regenerate_problem_statement"},
        },
    )
    assert destination == "problem_statement_agent"
    assert plan.reasoning_summary == "User approved dependency-resolution update."
