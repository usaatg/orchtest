from __future__ import annotations

import json
from pathlib import Path

from orchestrator_agents.routing import RoutingService
from orchestrator_agents.routing.policy import RISK_THRESHOLDS
from orchestrator_agents.schemas import RoutePlan, RouteStep, RouteVerification
from orchestrator_agents.routing.policy import apply_route_plan_policy

CASES = Path(__file__).parent / "routing_cases"


def test_golden_routes():
    examples = json.loads((CASES / "golden_routes.json").read_text())
    router = RoutingService()
    for ex in examples:
        plan, verification, destination, _reason = router.decide_plan(ex["query"])
        assert verification.approved is True
        assert destination == ex["expected_destination"], ex
        assert plan.mode == ex["expected_mode"], ex
        if "expected_steps" in ex:
            assert [s.agent for s in plan.steps] == ex["expected_steps"]


def test_adversarial_routes():
    examples = json.loads((CASES / "adversarial_routes.json").read_text())
    router = RoutingService()
    for ex in examples:
        _plan, _verification, destination, _reason = router.decide_plan(ex["query"])
        assert destination in ex["acceptable_destinations"], ex


def test_ambiguous_request_goes_to_clarification():
    plan, _verification, destination, _reason = RoutingService().decide_plan(
        "Can you help with this thing?"
    )
    assert plan.requires_clarification is True
    assert destination == "clarification_node"


def test_unknown_answerable_request_goes_to_fallback():
    plan, _verification, destination, _reason = RoutingService().decide_plan("What is 2 + 2?")
    assert plan.mode == "fallback"
    assert destination == "fallback_agent"


def test_risk_aware_threshold_blocks_low_confidence_medium_risk_agent():
    plan = RoutePlan(
        mode="single_agent",
        steps=[RouteStep(step_id="s1", agent="coding_agent", task="Write code", output_key="code")],
        confidence=RISK_THRESHOLDS["medium"] - 0.01,
        ambiguity_score=0.01,
        requires_clarification=False,
        reasoning_summary="Forced low confidence coding route for test.",
    )
    destination, reason = apply_route_plan_policy(
        plan, RouteVerification(approved=True, confidence=1.0, reason="test")
    )
    assert destination == "clarification_node"
    assert "below required" in reason


def test_required_input_validation_blocks_missing_user_query():
    plan, _verification, destination, reason = RoutingService().decide_plan(
        "Build Python code", state={"thread_id": "t1"}
    )
    assert "user_query" in plan.missing_inputs
    assert destination == "clarification_node"
    assert "missing required inputs" in reason
