from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional, Protocol
from pydantic import BaseModel, Field

AgentName = Literal[
    "research_agent",
    "coding_agent",
    "writing_agent",
    "smart_form_builder_agent",
    "problem_statement_agent",
]
ControlDestination = Literal["clarification_node", "fallback_agent", "finalizer"]
Destination = Literal[
    "research_agent",
    "coding_agent",
    "writing_agent",
    "smart_form_builder_agent",
    "problem_statement_agent",
    "clarification_node",
    "fallback_agent",
    "finalizer",
]
RouteMode = Literal["single_agent", "multi_agent", "clarification", "fallback", "dependency_resolution"]
RiskLevel = Literal["low", "medium", "high"]
ArtifactType = Literal[
    "research_summary",
    "code_output",
    "writing_output",
    "smart_form",
    "problem_statement",
]
ArtifactStatus = Literal["current", "stale", "superseded", "archived"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentSpec(BaseModel):
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
    primary_intent: str
    target_agent: Destination
    confidence: float = Field(ge=0.0, le=1.0)
    second_best_agent: Optional[Destination] = None
    second_best_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    requires_clarification: bool
    clarification_question: Optional[str] = None
    missing_inputs: list[str] = Field(default_factory=list)
    reasoning_summary: str


class RouteStep(BaseModel):
    step_id: str
    agent: AgentName
    task: str
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_key: str


class RoutePlan(BaseModel):
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
        if self.mode == "clarification":
            return "clarification_node"
        if self.mode == "fallback":
            return "fallback_agent"
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


class ArtifactDependency(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType | str
    version: int


class ArtifactRecord(BaseModel):
    artifact_id: str
    user_id: str
    namespace: tuple[str, ...]
    artifact_type: ArtifactType | str
    content: str
    summary: str
    version: int = 1
    status: ArtifactStatus = "current"
    source_thread_id: Optional[str] = None
    created_by: str = "unknown"
    created_at: str = Field(default_factory=utc_now)
    supersedes: Optional[str] = None
    depends_on: list[ArtifactDependency] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


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


# Direct-callable smart form agent contract.
FieldType = Literal["text", "email", "phone", "number", "date", "choice"]
FormStatus = Literal["not_started", "in_progress", "ready_for_review", "completed", "cancelled"]


class FormFieldSpec(BaseModel):
    name: str
    label: str
    required: bool = True
    field_type: FieldType = "text"
    choices: list[str] | None = None


class FormSchema(BaseModel):
    form_id: str
    form_name: str
    fields: list[FormFieldSpec]


class FormSessionState(BaseModel):
    form_id: str
    status: FormStatus = "not_started"
    fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    validation_errors: dict[str, str] = Field(default_factory=dict)
    current_field: str | None = None
    pending_question: str | None = None


class FormAgentInput(BaseModel):
    user_message: str
    form_schema: FormSchema
    form_state: FormSessionState | None = None
    user_id: str | None = None
    thread_id: str | None = None
    caller: Literal["direct", "orchestrator"] = "direct"


class FormAgentOutput(BaseModel):
    status: Literal["in_progress", "ready_for_review", "completed", "cancelled", "error"]
    updated_form_state: FormSessionState
    assistant_message: str
    result_summary: str
    completed: bool = False
    requires_user_input: bool = True
    artifact_payload: dict[str, Any] | None = None


# Direct-callable problem statement agent contract.
class ProblemStatementInput(BaseModel):
    user_message: str = ""
    form_artifact_id: str
    form_artifact_version: int
    form_content: dict[str, Any]
    previous_problem_statement_artifact_id: str | None = None
    update_reason: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    caller: Literal["direct", "orchestrator"] = "direct"


class ProblemStatementOutput(BaseModel):
    problem_statement: str
    assistant_message: str
    result_summary: str
    artifact_payload: dict[str, Any]
    depends_on: list[ArtifactDependency]
    supersedes: str | None = None
    completed: bool = True


class DependencyEvent(BaseModel):
    event_type: Literal["artifact_invalidated", "artifact_superseded", "dependency_resolved"]
    source_artifact_id: str
    new_artifact_id: str | None = None
    affected_artifact_id: str | None = None
    reason: str
    created_at: str = Field(default_factory=utc_now)


class BaseSubAgent(Protocol):
    name: AgentName

    def invoke(self, task: AgentTask, artifact_store: Any) -> AgentResult:
        ...
