from orchestrator_agents.routing import RoutingService


def test_routes_coding_request():
    decision, verification, destination = RoutingService().decide(
        "Can you build a LangGraph workflow with tests?"
    )
    assert decision.primary_intent == "coding"
    assert verification.approved is True
    assert destination == "coding_agent"


def test_routes_research_request():
    decision, verification, destination = RoutingService().decide(
        "Find the latest LangGraph handoff docs and cite sources"
    )
    assert decision.primary_intent == "research"
    assert verification.approved is True
    assert destination == "research_agent"


def test_routes_writing_request():
    decision, verification, destination = RoutingService().decide(
        "Rewrite this email to sound more professional"
    )
    assert decision.primary_intent == "writing"
    assert verification.approved is True
    assert destination == "writing_agent"


def test_ambiguous_request_goes_to_clarification():
    decision, _verification, destination = RoutingService().decide("Can you help with this thing?")
    assert decision.requires_clarification is True
    assert destination == "clarification_node"
