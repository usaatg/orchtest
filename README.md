# Orchestrator + Reusable Subagents Example v3

This repository demonstrates a production-oriented LangGraph-style architecture for an **orchestrator agent** that routes user requests to reusable, stateless subagents while preserving multi-turn workflow state with a user-facing `thread_id`.

Version 3 extends the v2.1 baseline with:

- Direct-callable subagents that can also be called by the orchestrator.
- A **Smart Form Builder Agent** that supports multi-turn form filling.
- A **Problem Statement Agent** that consumes smart form artifacts.
- Versioned artifacts, artifact lineage, and downstream dependency invalidation.
- Sticky routing for active form workflows and dependency-resolution confirmations.
- Tests for direct agent usage, routing, artifact dependency invalidation, and context packaging.

---

## Audience

This README is written for three audiences:

- **Product managers** who need to understand the user/workflow behavior.
- **Architects** who need to understand state, routing, dependencies, and extensibility.
- **Developers** who need to run, test, and extend the codebase.

---

## Product-Level Summary

The system has one user-facing orchestrator that receives all user messages. The orchestrator decides which specialist subagent should handle the request.

Current subagents:

1. `research_agent`
2. `coding_agent`
3. `writing_agent`
4. `smart_form_builder_agent`
5. `problem_statement_agent`

The most important v3 scenario is:

```text
User wants to define a business problem
  ↓
Orchestrator routes to Smart Form Builder Agent
  ↓
Smart Form Builder collects structured fields over multiple turns
  ↓
Completed smart form is saved as a versioned artifact
  ↓
Problem Statement Agent consumes latest form artifact
  ↓
Problem statement is saved as a versioned artifact that depends on the form artifact
  ↓
If form is later updated, orchestrator marks dependent problem statement stale
  ↓
Orchestrator asks whether user wants to regenerate/update the problem statement
```

This enables a more realistic multi-agent product workflow where downstream outputs know which upstream data they were generated from.

---

## Key Design Principles

### 1. One user-facing workflow thread

A UI application should generally create one stable `thread_id` per workflow session.

```text
Same workflow/session = same thread_id
New independent workflow/session = new thread_id
```

The `thread_id` belongs to the orchestrator workflow, not to individual subagents.

### 2. Subagents are stateless by default

Subagents should not own hidden mutable conversation state. They receive explicit input and return explicit output.

Generic subagent contract:

```python
AgentTask -> AgentResult
```

Smart form direct contract:

```python
FormAgentInput -> FormAgentOutput
```

Problem statement direct contract:

```python
ProblemStatementInput -> ProblemStatementOutput
```

This makes subagents reusable as:

- direct agents called by a UI/API, or
- orchestrator-managed subagents inside a larger workflow.

### 3. Orchestrator owns workflow state

The orchestrator state owns:

- `thread_id`
- `run_id`
- `active_workflow`
- `route_plan`
- `handoff_history`
- `latest_form_artifact_id`
- `latest_problem_statement_artifact_id`
- `pending_dependency_action`
- `stale_artifact_ids`

### 4. Artifact store owns durable outputs

Large or durable outputs should be stored as artifacts. Graph state should store IDs and short summaries, not entire long outputs.

Examples:

- completed smart form
- generated problem statement
- research summary
- coding plan
- writing output

### 5. Dependencies are tracked through artifact lineage

A problem statement artifact records that it depends on a specific form artifact version.

If the form artifact is superseded, the orchestrator can detect that the problem statement is stale.

---

## Repository Structure

```text
src/orchestrator_agents/
  agents/
    base.py
    coding.py
    research.py
    writing.py
    smart_form.py
    problem_statement.py
  graph/
    build.py
    context.py
    state.py
  routing/
    deterministic.py
    llm_router.py
    policy.py
    service.py
    verifier.py
  storage/
    artifact_store.py
    memory_store.py
  dependencies.py
  observability.py
  registry.py
  schemas.py
  cli.py

tests/
  test_artifact_memory.py
  test_context_packaging.py
  test_form_and_problem_agents.py
  test_graph_multiturn.py
  test_routing.py
  test_routing_form_problem_dependency.py
```

---

## Core Runtime Concepts

### `thread_id`

Identifies the user-facing workflow session. Reuse the same `thread_id` for multi-turn continuity.

### `run_id`

Identifies one graph invocation/turn.

### `handoff_id`

Identifies one delegation event from the orchestrator to a subagent.

### `task_id`

Identifies one route-plan step/subtask.

### `artifact_id`

Identifies a persisted output, such as a completed form or problem statement.

---

## Smart Form Builder Agent

The smart form agent is both:

1. a direct-callable agent, and
2. an orchestrator-callable subagent.

### Direct usage

```python
from orchestrator_agents.agents import DEFAULT_PROBLEM_FORM_SCHEMA, SmartFormBuilderAgent
from orchestrator_agents.schemas import FormAgentInput

agent = SmartFormBuilderAgent()
form_state = None

output = agent.run(
    FormAgentInput(
        user_message="I want to define a problem",
        form_schema=DEFAULT_PROBLEM_FORM_SCHEMA,
        form_state=form_state,
    )
)

form_state = output.updated_form_state
print(output.assistant_message)
```

The caller owns and persists `form_state` in direct mode.

### Orchestrator usage

The orchestrator converts `OrchestratorState` into an `AgentTask`; the smart form agent returns an `AgentResult` containing the updated `form_state` inside `metadata`.

While the form is active, the orchestrator sets:

```python
active_workflow = "form_fill"
```

This enables sticky routing so messages like `Mike Jones` or `Plant managers` go back to the form agent instead of being misclassified.

---

## Problem Statement Agent

The problem statement agent consumes the latest smart form artifact.

Direct contract:

```python
ProblemStatementInput -> ProblemStatementOutput
```

Orchestrated contract:

```python
AgentTask -> AgentResult
```

When called by the orchestrator, it expects:

```python
latest_form_artifact_id
```

It loads that artifact from `JsonArtifactStore`, generates a problem statement, and saves a new `problem_statement` artifact.

The new problem statement artifact records:

```python
depends_on = [form_artifact]
```

---

## Artifact Lineage and Dependency Handling

The v3 codebase adds artifact lineage.

### Example

```text
form_v1
  ↓
problem_statement_v1 depends_on form_v1
```

If the form is updated:

```text
form_v2 supersedes form_v1
```

The dependency checker finds downstream artifacts that depend on `form_v1` and marks them stale:

```text
problem_statement_v1.status = stale
```

Then the orchestrator creates a pending dependency action:

```python
pending_dependency_action = {
    "type": "offer_regenerate_problem_statement",
    "stale_artifact_ids": [...],
    "reason": "Form artifact changed; dependent problem statement may be stale.",
}
```

The user is asked:

```text
I updated the form. Your current problem statement was generated from the previous form version, so it may no longer be accurate. Would you like me to update the problem statement too?
```

If the user says `yes`, sticky dependency routing sends the next turn to `problem_statement_agent`.

---

## Routing Pipeline

Routing is handled by `RoutingService`.

```text
deterministic router
  ↓
LLM router placeholder if deterministic router cannot decide
  ↓
route verifier
  ↓
policy gate
  ↓
Command(goto=selected_agent)
```

The current implementation uses high-precision deterministic routing and a mock LLM router placeholder.

Production replacement:

```python
router_llm.with_structured_output(RoutePlan).invoke(...)
```

### Sticky routing

Before normal intent classification, the router checks active workflow state:

- `active_workflow == "form_fill"`
- `active_workflow == "dependency_resolution"`

This prevents short follow-up answers from being routed incorrectly.

---

## Graph Handoff Pattern

The orchestrator uses `Command(goto=...)` for dynamic routing.

Conceptually:

```text
START
  ↓
initialize
  ↓
import_context
  ↓
route
  ↓
route_policy
  ├── research_agent
  ├── coding_agent
  ├── writing_agent
  ├── smart_form_builder_agent
  ├── problem_statement_agent
  ├── clarification_node
  └── fallback_agent
```

After a subagent runs, its result goes back to the graph through shared state. The finalizer or route-plan executor decides what happens next.

The subagent does **not** own the user-facing interaction.

---

## Dynamic Graph Visualization Note

Because runtime handoffs use `Command(goto=...)`, visual graph renderers may show some nodes as disconnected or may not show all runtime edges. That does not necessarily mean the graph is wrong.

Static edges show graph structure. `Command(goto=...)` represents runtime routing.

---

## Memory vs State vs Artifacts

### Graph state

Active workflow working memory:

- active form state
- route plan
- pending dependency action
- selected agent
- current step index

### Artifact store

Durable outputs:

- completed form
- problem statement
- research summary
- code plan

### Memory store

Long-term user/project/agent knowledge. The demo includes a simple JSON-backed memory store; production should use a durable database/vector/document store as appropriate.

---

## Running Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

Expected test result in the build environment:

```text
15 passed, 2 skipped
```

The skipped tests are LangGraph runtime tests that only run when `langgraph` is installed.

---

## Production Notes

Before production use, replace or extend:

1. `JsonArtifactStore` with Postgres/blob/document storage.
2. `JsonMemoryStore` with durable user/project memory.
3. mock `llm_route_plan()` with a real structured-output LLM router.
4. observability state events with LangSmith/OpenTelemetry/log backend events.
5. demo checkpointer with a durable LangGraph checkpointer.
6. simple form extraction with more robust field extraction/validation.
7. stringified artifact content with JSON-native serialization.

---

## Recommended Product Behavior

When form data changes after a problem statement exists, do not silently regenerate everything.

Recommended default:

```text
Update form
Mark dependent problem statement stale
Ask user whether to update problem statement
If yes, regenerate from latest form
If no, keep stale artifact and show status when relevant
```

This gives users control and preserves artifact lineage.

---

## Extension Pattern

To add another dependent subagent, such as `solution_design_agent`:

1. Add an `AgentSpec` to `registry.py`.
2. Implement direct and orchestrated contracts.
3. Save outputs as artifacts.
4. Add `depends_on` references to source artifacts.
5. Add routing rules.
6. Add dependency invalidation behavior if source artifacts change.
7. Add tests for direct usage, routing, and dependency stale behavior.

This lets the architecture scale from two dependent agents to a full graph of generated deliverables:

```text
smart_form
  ↓
problem_statement
  ↓
solution_design
  ↓
implementation_plan
  ↓
executive_summary
```
