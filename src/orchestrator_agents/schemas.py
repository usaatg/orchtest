from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

AgentName = Literal["research_agent", "coding_agent", "writing_agent"]
ControlDestination = Literal["clarification_node", "fallback_agent"]
Destination = Literal[
    "research_agent",
    "coding_agent",
    "writing_agent",
    "clarification_node",
    "fallback_agent",
]
RouteMode = Literal["single_agent", "multi_agent", "clarification", "fallback"]
RiskLevel = Literal["low", "medium", "high"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentSpec(BaseModel):
    """Metadata used by the reusable router instead of hardcoding agent behavior."""

    name: AgentName
    description: str
    owns_intents: list[str]
    positive_examples: list[str]
    negative_examples: list[str]
    required_state_fields: list[str] = Field(default_factory=lambda: ["user_query"])
    risk_level: RiskLevel = "low"
    enabled: bool = True
    confidence_threshold_override: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RouteDecision(BaseModel):
    """A single-agent route proposal."""

    primary_intent: str
    target_agent: Destination
    confidence: float = Field(ge=0.0, le=1.0)
    second_best_agent: Optional[Destination] = None
    second_best_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    requires_clarification: bool
    clarification_question: Optional[str] = None
    missing_inputs: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(
        description="Brief user-safe reason. Do not include hidden chain-of-thought."
    )


class RouteStep(BaseModel):
    """One step in a route plan. Allows multi-agent workflows."""

    step_id: str
    agent: AgentName
    task: str
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_key: str


class RoutePlan(BaseModel):
    """The router proposes a plan; the policy gate decides whether it may run."""

    mode: RouteMode
    steps: list[RouteStep] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    second_best_agent: Optional[Destination] = None
    second_best_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    requires_clarification: bool
    clarification_question: Optional[str] = None
    fallback_reason: Optional[str] = None
    missing_inputs: list[str] = Field(default_factory=list)
    reasoning_summary: str

    @property
    def first_destination(self) -> Destination:
        if self.mode in {"clarification", "fallback"}:
            return "clarification_node" if self.mode == "clarification" else "fallback_agent"
        if not self.steps:
            return "fallback_agent"
        return self.steps[0].agent


class RouteVerification(BaseModel):
    approved: bool
    corrected_destination: Optional[Destination] = None
    corrected_plan: Optional[RoutePlan] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class ImportedContext(BaseModel):
    source_thread_id: Optional[str] = None
    source_artifact_id: Optional[str] = None
    content: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecord(BaseModel):
    artifact_id: str
    user_id: str
    namespace: tuple[str, ...]
    artifact_type: str
    content: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_thread_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now)


class MemoryRecord(BaseModel):
    memory_id: str
    user_id: str
    namespace: tuple[str, ...]
    memory_type: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class ObservabilityEvent(BaseModel):
    event_type: str
    thread_id: str
    run_id: str
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    handoff_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class HandoffEvent(BaseModel):
    handoff_id: str
    thread_id: str
    run_id: str
    from_agent: str
    to_agent: Destination
    task_id: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    created_at: str = Field(default_factory=utc_now)


class AgentTask(BaseModel):
    task_id: str
    target_agent: AgentName
    user_query: str
    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    task_id: str
    agent_name: AgentName
    result: str
    result_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    artifact_ids: list[str] = Field(default_factory=list)
    needs_followup: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
