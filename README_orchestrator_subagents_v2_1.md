# Orchestrator + Stateless Subagents Example

A production-oriented LangGraph reference implementation for a multi-turn orchestrator agent that routes user requests to specialized stateless subagents.

This repository demonstrates how to build an agentic workflow where one orchestrator receives all user-facing messages, determines the correct route, delegates to the appropriate subagent or subagents, persists workflow context using a stable `thread_id`, and stores durable outputs outside graph state using artifact and memory stores.

The design is intentionally modular so product managers, architects, and developers can understand, extend, and reuse the routing and orchestration patterns across multiple agentic products.

---

## 1. Executive Summary

This repo implements a reusable agentic workflow architecture with:

- One **orchestrator graph** that owns the user-facing workflow.
- Three **stateless subagents**:
  - `research_agent`
  - `coding_agent`
  - `writing_agent`
- A reusable **routing control plane** that decides which subagent or sequence of subagents should handle each request.
- Multi-turn conversation support through a stable `thread_id`.
- Cross-thread reference support through curated artifact imports.
- Durable output storage through an `ArtifactStore`.
- Durable user/project/agent knowledge storage through a separate `MemoryStore`.
- Structured observability for route decisions, handoffs, subagent completion, and context imports.
- Golden and adversarial tests to make routing behavior measurable and regression-safe.

The core principle is:

```text
The orchestrator owns workflow state.
Subagents are stateless workers.
Durable outputs live in artifact storage.
Reusable knowledge lives in memory storage.
Routing decisions pass through policy, not direct LLM control.
```

---

## 2. Intended Audience

### Product Managers

Use this repo to understand:

- What the agentic system can do.
- How requests are routed to specialist agents.
- How multi-turn workflow continuity works.
- Why clarification is sometimes better than guessing.
- What future product extensions are possible.

### Architects

Use this repo to evaluate:

- State ownership boundaries.
- Thread/session identity patterns.
- Subagent statelessness.
- Routing policy and verification layers.
- Artifact and memory separation.
- Production persistence requirements.
- Observability and auditability.

### Developers

Use this repo to implement:

- LangGraph orchestrator workflows.
- `Command(goto=...)` dynamic handoffs.
- Stateless subagent interfaces.
- Reusable routing services.
- Route-plan execution.
- Context packaging.
- Artifact and memory stores.
- Automated routing tests.

---

## 3. Repository Structure

```text
orchestrator-subagents-example/
  pyproject.toml
  .env.example
  README.md

  src/orchestrator_agents/
    __init__.py
    cli.py
    registry.py
    schemas.py
    observability.py

    agents/
      __init__.py
      base.py
      research.py
      coding.py
      writing.py

    graph/
      __init__.py
      build.py
      context.py
      state.py

    routing/
      __init__.py
      deterministic.py
      llm_router.py
      policy.py
      service.py
      verifier.py

    storage/
      __init__.py
      artifact_store.py
      memory_store.py

  tests/
    test_artifact_memory.py
    test_context_packaging.py
    test_graph_multiturn.py
    test_routing.py

    routing_cases/
      golden_routes.json
      adversarial_routes.json
```

---

## 4. High-Level Architecture

```text
User / UI
  |
  v
LangGraph Orchestrator Graph
  |
  +--> initialize
  |
  +--> import_context
  |
  +--> route
  |      |
  |      +--> deterministic router
  |      +--> mocked LLM router fallback
  |      +--> required input validation
  |      +--> route verifier
  |      +--> policy gate
  |
  +--> route_policy
         |
         +--> clarification_node
         +--> fallback_agent
         +--> research_agent
         +--> coding_agent
         +--> writing_agent
                  |
                  v
              next_step
                  |
                  +--> next subagent if multi-agent plan
                  +--> finalizer if done
```

The orchestrator is responsible for receiving the user query, normalizing it, optionally importing prior context, selecting the right route, delegating to one or more subagents, collecting outputs, and producing the final answer.

The subagents are deliberately simple and stateless. They do not own hidden conversation memory. They receive an `AgentTask`, perform their specialized work, save durable outputs as artifacts, and return an `AgentResult`.

---

## 5. Core Design Principles

### 5.1 The Orchestrator Owns Workflow State

The orchestrator graph owns:

- `thread_id`
- `run_id`
- `route_plan`
- `route_verification`
- `route_history`
- `handoff_history`
- `observability_events`
- `current_route_step_index`
- `selected_agent`
- `current_agent`
- artifact IDs
- final answer

This keeps the user-facing workflow coherent and auditable.

### 5.2 Subagents Are Stateless by Default

Subagents follow this contract:

```text
AgentTask -> AgentResult
```

They should not own hidden mutable state. They should not decide which subagent runs next. They should not persist workflow state privately.

This makes subagents:

- easier to test,
- easier to scale,
- easier to reuse,
- easier to debug,
- safer to run in parallel,
- less likely to pollute routing decisions with stale context.

### 5.3 Routing Is a Control Plane

Routing is not just a prompt. It is a subsystem with:

1. deterministic high-precision routing,
2. LLM fallback routing,
3. required input validation,
4. route verification,
5. deterministic policy gate,
6. observability events,
7. tests.

The router proposes. The verifier and policy gate approve or redirect.

### 5.4 State, Artifacts, and Memory Are Different Things

```text
Graph state
  Active workflow working memory needed to continue execution.

Artifact store
  Durable generated outputs, reports, summaries, code, and reusable artifacts.

Memory store
  Durable user/project/agent facts and preferences that may outlive one workflow.
```

The graph state should stay compact. Large outputs should be stored as artifacts and referenced by ID.

---

## 6. Thread IDs, Sessions, and Multi-Turn Conversations

### 6.1 What `thread_id` Means

In this repo, `thread_id` represents a user-facing workflow session.

```text
One UI workflow session = one thread_id
```

Use the same `thread_id` when the user is continuing the same workflow context.

Use a new `thread_id` when the user starts a new independent workflow.

### 6.2 Example UI Model

A UI application might store:

```text
users
  user_id

workflow_sessions
  session_id
  user_id
  workflow_type
  langgraph_thread_id
  status
  created_at
  updated_at
```

Example:

```json
{
  "user_id": "user_123",
  "workflow_type": "orchestrator_assistant",
  "thread_id": "workflow_session_abc123"
}
```

Every follow-up in that same workflow uses the same `thread_id`.

### 6.3 Same Thread vs New Thread

Use the same thread when the user says:

```text
"Now modify that."
"Continue from the previous answer."
"Add another step to this workflow."
"Use the same context."
```

Create a new thread when the user says or implies:

```text
"Start over."
"New project."
"Separate analysis."
"Do not use previous context."
```

### 6.4 Cross-Thread References

This repo supports starting a new thread while referencing prior work.

Use:

```python
referenced_thread_ids: list[str]
referenced_artifact_ids: list[str]
```

The important rule is:

```text
Do not load the full old thread into the new thread.
Import curated summaries or artifact references only.
```

This keeps the new workflow clean while still allowing reuse of prior outputs.

---

## 7. Identity Model

The codebase uses several IDs intentionally. They should not be collapsed into one field.

| Identifier | Meaning |
|---|---|
| `user_id` | The end user or application user. |
| `thread_id` | The user-facing workflow session. |
| `run_id` | One graph invocation/turn within a thread. |
| `handoff_id` | One delegation from orchestrator to a subagent. |
| `task_id` | One route-plan step or subtask. |
| `agent_id` | The component currently executing. |
| `artifact_id` | A durable stored output. |
| `memory_id` | A durable stored memory record. |

Example handoff:

```json
{
  "handoff_id": "handoff_abc123",
  "thread_id": "thread_001",
  "run_id": "run_001",
  "from_agent": "orchestrator",
  "to_agent": "coding_agent",
  "task_id": "step_1234",
  "confidence": 0.9,
  "reason": "Route plan passed policy gate."
}
```

---

## 8. Request Lifecycle

A single user turn flows through the graph like this.

### Step 1: `initialize`

Defined in:

```text
src/orchestrator_agents/graph/build.py
```

Responsibilities:

- create or reuse `run_id`,
- normalize `user_query`,
- reset turn-scoped `final_answer`,
- reset `current_route_step_index`,
- emit `request_normalized` event.

Important detail:

`final_answer` is reset each turn so checkpointed multi-turn sessions do not accidentally return a previous response.

### Step 2: `import_context`

Responsibilities:

- load summaries from `referenced_artifact_ids`,
- load summaries from artifacts produced in `referenced_thread_ids`,
- append them to `imported_context`,
- keep full artifact content in the artifact store.

The graph imports curated summaries, not full artifact content.

### Step 3: `route`

Responsibilities:

- ask `RoutingService` for a route plan,
- record the route plan,
- record route verification,
- record selected destination,
- emit `route_selected` event.

### Step 4: `route_policy`

Responsibilities:

- inspect selected destination,
- create a `HandoffEvent` if routing to a subagent,
- use `Command(goto=...)` for runtime handoff.

### Step 5: Subagent Execution

One of:

- `research_agent`
- `coding_agent`
- `writing_agent`

Responsibilities:

- receive packaged `AgentTask`,
- perform work,
- save full output to artifact store,
- return structured `AgentResult`,
- emit `subagent_completed` event.

### Step 6: `next_step`

Responsibilities:

- check whether the `RoutePlan` has another step,
- hand off to the next subagent if needed,
- otherwise route to `finalizer`.

### Step 7: `finalizer`

Responsibilities:

- combine recent agent results,
- produce `final_answer`,
- append a final assistant message.

---

## 9. Routing System

Routing code lives in:

```text
src/orchestrator_agents/routing/
```

### 9.1 `deterministic.py`

Defines high-precision rules for common cases.

Examples:

- coding terms route to `coding_agent`,
- research terms route to `research_agent`,
- writing terms route to `writing_agent`,
- research + coding terms create a multi-agent route plan:

```text
research_agent -> coding_agent
```

The deterministic router should only contain high-confidence rules. It should avoid overly broad keyword matching.

### 9.2 `llm_router.py`

Currently a mock fallback router.

In production, replace this with a structured-output LLM call that returns a `RoutePlan`.

The LLM router should:

- classify the user’s intent,
- choose one or more route steps,
- provide confidence,
- report ambiguity,
- ask for clarification if needed,
- not perform the task itself.

### 9.3 `service.py`

`RoutingService` is the reusable routing orchestration layer.

It performs:

```text
deterministic route plan
  OR mocked LLM route plan
  -> required input validation
  -> route verification
  -> policy gate
```

Primary API:

```python
plan, verification, destination, policy_reason = routing_service.decide_plan(
    user_query,
    state=state,
)
```

### 9.4 `verifier.py`

Validates the proposed route plan before policy approval.

Current verifier checks:

- control modes are allowed,
- executable plans have steps,
- every step references a registered agent,
- every referenced agent is enabled.

In production, you can add an LLM-based verifier for ambiguous or high-risk routes.

### 9.5 `policy.py`

The deterministic gate that decides whether the route may execute.

It checks:

- verifier approval,
- clarification requirement,
- fallback mode,
- empty plan,
- ambiguity score,
- confidence margin between top candidates,
- missing required inputs,
- risk-aware confidence threshold.

This is the key production principle:

```text
The LLM or deterministic router proposes.
The policy gate decides.
```

---

## 10. Route Plans

A `RoutePlan` supports both single-agent and multi-agent workflows.

Defined in:

```text
src/orchestrator_agents/schemas.py
```

```python
class RoutePlan(BaseModel):
    mode: Literal["single_agent", "multi_agent", "clarification", "fallback"]
    steps: list[RouteStep]
    confidence: float
    second_best_agent: Optional[Destination]
    second_best_confidence: Optional[float]
    ambiguity_score: float
    requires_clarification: bool
    clarification_question: Optional[str]
    fallback_reason: Optional[str]
    missing_inputs: list[str]
    reasoning_summary: str
```

A single-agent plan:

```text
coding_agent
```

A multi-agent plan:

```text
research_agent -> coding_agent
```

Example user request:

```text
Research the latest LangGraph handoff patterns and build an implementation.
```

Expected route plan:

```text
research_agent -> coding_agent
```

This allows the orchestrator to handle compound tasks without forcing one subagent to do everything.

---

## 11. Agent Registry

Agent definitions live in:

```text
src/orchestrator_agents/registry.py
```

Each agent has an `AgentSpec`:

```python
class AgentSpec(BaseModel):
    name: AgentName
    description: str
    owns_intents: list[str]
    positive_examples: list[str]
    negative_examples: list[str]
    required_state_fields: list[str]
    risk_level: Literal["low", "medium", "high"]
    enabled: bool
    confidence_threshold_override: Optional[float]
```

The registry is the source of truth for:

- what agents exist,
- what they are responsible for,
- what examples they own or do not own,
- what state fields are required,
- how risky they are,
- whether they are enabled.

Adding a new subagent should generally start by adding a new `AgentSpec`.

---

## 12. Risk-Aware Routing

Defined in:

```text
src/orchestrator_agents/routing/policy.py
```

Current thresholds:

```python
RISK_THRESHOLDS = {
    "low": 0.70,
    "medium": 0.78,
    "high": 0.85,
}
```

A high-risk agent requires higher confidence before the policy gate allows execution.

This matters because routing mistakes are not equally costly. A writing mistake is usually lower impact than a production deployment, financial analysis, or regulated-domain action.

---

## 13. Context Packaging

Context packaging lives in:

```text
src/orchestrator_agents/graph/context.py
```

The orchestrator does not pass the full graph state to every subagent. Instead, it builds an `AgentTask` with only relevant context.

```python
AgentTask(
    task_id=step.step_id,
    target_agent=agent_name,
    user_query=state["user_query"],
    instruction=step.task,
    context=context,
)
```

Common context fields:

- `user_id`
- `thread_id`
- `run_id`
- `route_step_index`
- `available_artifact_ids`
- `imported_context`

Agent-specific context examples:

| Agent | Additional Context |
|---|---|
| `coding_agent` | framework, preferred language |
| `research_agent` | recency requirement, source constraints |
| `writing_agent` | tone, audience |

This pattern prevents context pollution and keeps subagents reusable.

---

## 14. Subagents

Subagents live in:

```text
src/orchestrator_agents/agents/
```

### 14.1 Base Contract

Defined in:

```text
src/orchestrator_agents/agents/base.py
```

The intended contract is:

```text
AgentTask -> AgentResult
```

Each subagent should implement an `invoke(...)` method that receives an `AgentTask` and returns an `AgentResult`.

### 14.2 Research Agent

Defined in:

```text
src/orchestrator_agents/agents/research.py
```

Responsibilities:

- produce research-style summaries,
- use imported context when available,
- save full research output to artifact store,
- return artifact IDs in `AgentResult`.

### 14.3 Coding Agent

Defined in:

```text
src/orchestrator_agents/agents/coding.py
```

Responsibilities:

- produce implementation guidance,
- use prior research artifacts/context if available,
- save coding output to artifact store,
- return artifact IDs in `AgentResult`.

### 14.4 Writing Agent

Defined in:

```text
src/orchestrator_agents/agents/writing.py
```

Responsibilities:

- draft or rewrite content,
- respect tone/audience context,
- save writing output to artifact store,
- return artifact IDs in `AgentResult`.

---

## 15. Artifact Store

Artifact storage lives in:

```text
src/orchestrator_agents/storage/artifact_store.py
```

The demo implementation is `JsonArtifactStore`.

Artifacts are used for:

- full agent outputs,
- research summaries,
- generated code plans,
- writing outputs,
- reusable deliverables,
- cross-thread references.

The graph state carries artifact IDs, not large content.

Example namespace:

```text
("threads", thread_id, "artifacts")
```

Example artifact record:

```json
{
  "artifact_id": "artifact_abc123",
  "user_id": "user_123",
  "namespace": ["threads", "thread_001", "artifacts"],
  "artifact_type": "coding_result",
  "content": "Full generated implementation guidance...",
  "summary": "Short summary...",
  "source_thread_id": "thread_001"
}
```

Production replacements can include:

- Postgres,
- S3/blob storage,
- document stores,
- vector stores,
- artifact registries.

---

## 16. Memory Store

Memory storage lives in:

```text
src/orchestrator_agents/storage/memory_store.py
```

The demo implementation is `JsonMemoryStore`.

Memory is for durable facts and preferences, not generated outputs.

Use memory for:

- user preferences,
- project facts,
- agent-specific durable knowledge,
- reusable routing examples,
- long-term personalization.

Use artifacts for:

- generated reports,
- code outputs,
- research outputs,
- documents,
- workflow deliverables.

Recommended namespaces:

```text
("users", user_id, "memories")
("users", user_id, "agents", agent_name, "memory")
("users", user_id, "projects", project_id, "memory")
```

---

## 17. Observability

Observability helpers live in:

```text
src/orchestrator_agents/observability.py
```

Events are represented by `ObservabilityEvent` and appended to graph state.

Current event types include:

- `request_normalized`
- `context_imported`
- `route_selected`
- `handoff_created`
- `subagent_completed`

Example event:

```json
{
  "event_type": "route_selected",
  "thread_id": "thread_001",
  "run_id": "run_001",
  "agent_id": "coding_agent",
  "payload": {
    "mode": "single_agent",
    "confidence": 0.88,
    "policy_reason": "Route plan passed policy gate."
  }
}
```

In production, these events should be exported to:

- logs,
- LangSmith,
- OpenTelemetry,
- metrics dashboards,
- audit tables,
- incident/debug tooling.

---

## 18. Clarification vs Fallback

The code distinguishes two important outcomes.

### Clarification

Use when more user input is needed.

Example:

```text
"Can you help with my agent?"
```

The request is too ambiguous, so the system should ask a clarifying question.

### Fallback

Use when the task is answerable but no specialist fits.

Example:

```text
"What is 2 + 2?"
```

The fallback path handles general requests without pretending a specialist was selected.

This distinction helps routing correctness. The system should not force a specialist when the query is ambiguous or out of scope.

---

## 19. Dynamic Graph Handoffs with `Command(goto=...)`

The graph uses runtime handoffs through:

```python
Command(update={...}, goto="coding_agent")
```

This allows the orchestrator to decide the next node dynamically.

Important implication:

```text
Some graph visualizations may show nodes that appear disconnected.
```

This can happen because the destination is selected at runtime rather than through only static `add_edge(...)` calls.

This is expected when using dynamic routing patterns. The code documents possible destinations through type hints like `DestinationLiteral`.

---

## 20. Tests

Tests live in:

```text
tests/
```

### 20.1 Routing Tests

```text
tests/test_routing.py
```

Covers:

- golden routing examples,
- adversarial routing examples,
- clarification cases,
- missing required input validation,
- policy behavior.

### 20.2 Routing Case Files

```text
tests/routing_cases/golden_routes.json
tests/routing_cases/adversarial_routes.json
```

Golden cases represent normal expected behavior.

Adversarial cases represent ambiguous or tricky queries that are likely to expose routing mistakes.

### 20.3 Artifact and Memory Tests

```text
tests/test_artifact_memory.py
```

Covers:

- artifact store behavior,
- memory store behavior,
- namespace separation.

### 20.4 Context Packaging Tests

```text
tests/test_context_packaging.py
```

Covers:

- subagents receive packaged `AgentTask`,
- task IDs correlate with route steps,
- full state is not blindly passed to subagents.

### 20.5 Graph Multi-Turn Tests

```text
tests/test_graph_multiturn.py
```

Covers multi-turn graph behavior when LangGraph is installed.

Some graph runtime tests may be skipped if LangGraph is not installed in the local environment.

---

## 21. Running the Project

### 21.1 Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### 21.2 Run the Demo CLI

```bash
orchestrator-demo
```

### 21.3 Run Tests

```bash
pytest -q
```

### 21.4 Compile Check

```bash
python -m compileall -q src tests
```

---

## 22. Production Persistence

The demo uses local JSON stores and optional LangGraph checkpointing.

This is appropriate for local development, but production should use durable storage.

### Demo

```text
ArtifactStore -> local JSON files
MemoryStore   -> local JSON files
Checkpointer  -> optional local/in-memory checkpointing
```

### Production

Recommended production replacements:

```text
Checkpointer  -> Postgres, Redis, or other durable LangGraph-compatible backend
ArtifactStore -> S3/blob storage, Postgres, document store, artifact registry
MemoryStore   -> Postgres, vector store, document database, profile store
Observability -> OpenTelemetry, LangSmith, logs, metrics backend
```

Important:

```text
In-memory checkpointing is not durable across restarts.
```

If the product requires multi-turn continuity after deployment restarts, use a durable checkpointer.

---

## 23. Product Behavior Examples

### 23.1 Coding Request

User:

```text
Build a LangGraph workflow with a router and subagents.
```

Expected route:

```text
coding_agent
```

### 23.2 Research Request

User:

```text
Research the latest LangGraph handoff docs.
```

Expected route:

```text
research_agent
```

### 23.3 Writing Request

User:

```text
Rewrite this email to sound more executive.
```

Expected route:

```text
writing_agent
```

### 23.4 Multi-Agent Request

User:

```text
Research the latest LangGraph patterns and create implementation guidance.
```

Expected route:

```text
research_agent -> coding_agent
```

### 23.5 Ambiguous Request

User:

```text
Can you help with my agent?
```

Expected route:

```text
clarification_node
```

### 23.6 General Request

User:

```text
What is 2 + 2?
```

Expected route:

```text
fallback_agent
```

---

## 24. How to Add a New Subagent

To add a new subagent, for example `analysis_agent`:

### Step 1: Add an Agent Name

Update `AgentName` and `Destination` in:

```text
src/orchestrator_agents/schemas.py
```

### Step 2: Add an AgentSpec

Update:

```text
src/orchestrator_agents/registry.py
```

Add:

```python
"analysis_agent": AgentSpec(
    name="analysis_agent",
    description="Handles analytical decomposition and structured evaluations.",
    owns_intents=["analysis", "evaluation"],
    positive_examples=[...],
    negative_examples=[...],
    risk_level="medium",
)
```

### Step 3: Implement the Subagent

Create:

```text
src/orchestrator_agents/agents/analysis.py
```

Follow the contract:

```python
def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
    ...
```

### Step 4: Register the Node

Update:

```text
src/orchestrator_agents/graph/build.py
```

Add the agent instance and graph node.

### Step 5: Update Routing

Update deterministic rules and/or the LLM router prompt/schema.

### Step 6: Add Tests

Add golden and adversarial route cases.

---

## 25. How to Replace the Mock LLM Router

The current `llm_router.py` is intentionally mocked so the repo can run without API credentials.

In production, replace it with a structured-output model call.

Expected behavior:

```python
def llm_route_plan(user_query: str) -> RoutePlan:
    return router_llm.with_structured_output(RoutePlan).invoke([
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ])
```

Router prompt principles:

- choose exactly one route mode,
- do not solve the user task,
- return confidence,
- return ambiguity score,
- return clarification question when needed,
- return one or more route steps,
- keep reasoning summary short and user-safe.

Do not allow the LLM router to directly execute tools or call subagents. It should only propose a route plan.

---

## 26. Security and Safety Considerations

For production systems, consider adding:

- authentication and authorization around thread and artifact access,
- per-user namespace isolation,
- artifact access control,
- audit logging for cross-thread references,
- PII redaction before storing artifacts,
- retention policies for old artifacts and checkpoints,
- model output validation,
- route-plan allowlists,
- tool permission policies per subagent,
- human approval gates for high-risk actions.

The current repo is a reference implementation, not a complete security boundary.

---

## 27. Known Limitations

This repo is a production-oriented reference, not a full production platform.

Known limitations:

- LLM routing is mocked.
- Artifact and memory stores are local JSON implementations.
- Observability events are stored in graph state, not exported to a backend.
- Multi-agent plans are sequential, not parallel fan-out/fan-in.
- Subagent outputs are illustrative, not real tool-using agents.
- Production-grade authentication, authorization, and data retention are not implemented.

---

## 28. Recommended Next Enhancements

High-value next steps:

1. Replace mock LLM router with structured-output LLM router.
2. Add an LLM verifier for ambiguous or high-risk route plans.
3. Add durable LangGraph checkpointer, such as Postgres or Redis.
4. Add real artifact storage backend.
5. Add real memory backend with semantic retrieval.
6. Export observability events to OpenTelemetry or LangSmith.
7. Add parallel `Send(...)` fan-out/fan-in workflows.
8. Add human-in-the-loop review nodes for high-risk workflows.
9. Add authorization checks for referenced artifacts and threads.
10. Add route metrics dashboards.

---

## 29. Glossary

| Term | Meaning |
|---|---|
| Orchestrator | The user-facing graph that owns routing and workflow state. |
| Subagent | A specialized stateless worker that handles one task. |
| Thread ID | User-facing workflow/session identifier. |
| Run ID | One graph invocation/turn. |
| Handoff | Delegation from orchestrator to a subagent. |
| Route Plan | Proposed execution plan with one or more subagent steps. |
| Policy Gate | Deterministic approval layer for route decisions. |
| Artifact | Durable generated output, such as research or code. |
| Memory | Durable reusable knowledge or preference. |
| Imported Context | Curated summaries brought from another artifact or thread. |
| Clarification Node | Asks the user for missing information. |
| Fallback Agent | Handles valid general requests with no matching specialist. |

---

## 30. Summary

This repository demonstrates a robust pattern for orchestrator-driven agentic workflows:

```text
UI/user sends message to orchestrator
  -> orchestrator normalizes request
  -> imports optional prior context
  -> router proposes route plan
  -> verifier validates route plan
  -> policy gate approves destination
  -> orchestrator dynamically hands off to stateless subagent(s)
  -> subagents produce results and artifacts
  -> finalizer returns answer
  -> thread state preserves multi-turn workflow context
```

The key production idea is that correct subagent selection is not just a prompt engineering problem. It is a routing architecture problem that requires typed schemas, explicit policies, observability, tests, and clean separation between workflow state, durable artifacts, and long-term memory.
