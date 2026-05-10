from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

AgentName = Literal["research_agent", "coding_agent", "writing_agent"]
Destination = Literal[
    "research_agent",
    "coding_agent",
    "writing_agent",
    "clarification_node",
    "fallback_agent",
]


class AgentSpec(BaseModel):
    """Metadata used by the reusable router.

    Agents are registered by capability instead of hardcoded throughout the graph.
    This makes the router reusable across workflows.
    """

    name: AgentName
    description: str
    owns_intents: list[str]
    positive_examples: list[str]
    negative_examples: list[str]
    required_state_fields: list[str] = Field(default_factory=lambda: ["user_query"])
    risk_level: Literal["low", "medium", "high"] = "low"
    enabled: bool = True


class RouteDecision(BaseModel):
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


class RouteVerification(BaseModel):
    approved: bool
    corrected_destination: Optional[Destination] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class AgentTask(BaseModel):
    task_id: str
    target_agent: AgentName
    user_query: str
    instruction: str
    context: dict = Field(default_factory=dict)


class AgentResult(BaseModel):
    task_id: str
    agent_name: AgentName
    result: str
    confidence: float = Field(ge=0.0, le=1.0)
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
