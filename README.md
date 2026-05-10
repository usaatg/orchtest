# Orchestrator + LangGraph Subagent Workflows — v4

This repository demonstrates a production-oriented **LangGraph orchestrator** that routes user requests to multiple **LangGraph subagent workflows**. The design is intended for teams building agentic systems where a central orchestrator controls routing, session state, artifact lineage, dependency invalidation, and final user-facing responses, while specialized agents can also be used independently.

## Audience

This README is written for three audiences:

- **Product managers** who need to understand capabilities, user flows, and product behavior.
- **Architects** who need to understand the system boundaries, state model, dependency model, and production scaling considerations.
- **Developers** who need to run, test, extend, and integrate the code.

---

## What changed in v4

v4 upgrades the v3 design so that the orchestrator and every subagent are represented as **LangGraph workflows**.

The repo now includes:

- `orchestrator_graph`: top-level user-facing workflow.
- `research_agent_graph`: direct/subagent-callable LangGraph workflow.
- `coding_agent_graph`: direct/subagent-callable LangGraph workflow.
- `writing_agent_graph`: direct/subagent-callable LangGraph workflow.
- `smart_form_builder_agent_graph`: multi-node LangGraph workflow for multi-turn form filling.
- `problem_statement_agent_graph`: multi-node LangGraph workflow that consumes smart form artifacts and produces problem statement artifacts.

The important architectural rule is that subagents are **not coupled to the orchestrator state schema**. They expose clean input/output contracts, and the orchestrator uses adapter logic to call them.

---

## Core product scenario

A user can interact with an orchestrated workflow like this:

```text
User: I want to define a business problem.
  ↓
Orchestrator routes to Smart Form Builder Agent Graph.
  ↓
Smart Form Builder asks structured questions across multiple turns.
  ↓
Completed smart form is saved as a versioned artifact.
  ↓
Orchestrator routes to Problem Statement Agent Graph.
  ↓
Problem Statement Agent generates a problem statement from the latest form artifact.
  ↓
Problem statement artifact depends_on the form artifact.
```

Later:

```text
User: Actually, update the stakeholder field in the form.
  ↓
Smart Form Builder updates the form and creates form v2.
  ↓
Dependency checker sees problem_statement v1 depends_on form v1.
  ↓
Problem statement is marked stale.
  ↓
Orchestrator asks whether the user wants the problem statement updated.
  ↓
If yes, Problem Statement Agent regenerates statement from form v2.
```

This pattern generalizes to any future chain of dependent artifacts:

```text
smart form → problem statement → solution design → implementation plan → executive summary
```

---

## High-level architecture

```text
UI / API
  ↓
Orchestrator LangGraph Workflow
  ├── routing service
  ├── route policy gate
  ├── handoff tracking
  ├── sticky workflow routing
  ├── dependency resolution
  ├── artifact lineage
  └── finalizer
       ↓
       ├── Research Agent LangGraph Workflow
       ├── Coding Agent LangGraph Workflow
       ├── Writing Agent LangGraph Workflow
       ├── Smart Form Builder Agent LangGraph Workflow
       └── Problem Statement Agent LangGraph Workflow
```

Each subagent graph can be used in two ways:

```text
Direct mode:
  UI/API → subagent graph

Orchestrated mode:
  UI/API → orchestrator graph → subagent graph → orchestrator/finalizer
```

---

## Repository structure

```text
orchestrator-subagents-example-v4/
  pyproject.toml
  README.md
  .env.example
  src/orchestrator_agents/
    agent_workflows/
      __init__.py
      _langgraph.py
      basic.py
      smart_form.py
      problem_statement.py
    agents/
      base.py
      research.py
      coding.py
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
    routing_cases/
    test_*.py
```

### Important folders

#### `agent_workflows/`

Contains the LangGraph workflows for subagents.

- `basic.py` builds one-node workflows for research/coding/writing.
- `smart_form.py` builds the Smart Form Builder LangGraph workflow.
- `problem_statement.py` builds the Problem Statement LangGraph workflow.

#### `agents/`

Contains reusable stateless agent logic. These classes still exist because they are useful as the internal business logic inside the subagent graphs.

Example:

```text
SmartFormBuilderAgent.run(FormAgentInput) -> FormAgentOutput
```

The graph wraps this service with workflow steps like normalization, validation, artifact persistence, and output normalization.

#### `graph/`

Contains the top-level orchestrator LangGraph workflow.

The orchestrator is responsible for:

- routing
- sticky workflow continuation
- invoking subagent graphs
- recording handoffs
- collecting outputs
- managing dependency resolution
- producing final answers

#### `storage/`

Contains local JSON-backed stores for demo purposes.

- `ArtifactStore`: stores generated outputs, completed forms, problem statements, etc.
- `MemoryStore`: stores durable reusable memory separate from workflow state.

For production, replace these with a durable backend.

---

## Key design principles

### 1. Orchestrator owns top-level control

The orchestrator owns:

- `thread_id`
- route decisions
- route plans
- handoff history
- active workflow state
- artifact lineage
- dependency invalidation
- user-facing final answers

Subagents do not directly decide the overall user workflow.

### 2. Subagents are LangGraph workflows

Each subagent is now a graph boundary. This allows subagents to have their own internal steps while remaining reusable.

For simple agents, the workflow may be a one-node graph:

```text
START → invoke_agent → END
```

For complex agents, the workflow has multiple nodes:

```text
Smart Form Builder:
START → normalize → run_form_logic → persist_artifact → END

Problem Statement:
START → load_form_artifact → draft_statement → persist_problem_statement → END
```

### 3. Subagents are still stateless from the caller's perspective

A subagent graph can have internal workflow state during invocation, but it should not hide durable state from the orchestrator.

The caller provides the current context:

```text
FormGraphInput includes current form state.
ProblemStatementGraphInput includes form artifact ID.
```

The subagent returns structured output:

```text
AgentResult
artifact IDs
assistant message
metadata
```

### 4. State, memory, and artifacts are different

```text
Graph state:
  Active workflow state needed to continue execution.

Artifact store:
  Versioned durable outputs such as completed forms and problem statements.

Memory store:
  Durable reusable knowledge/preferences across workflows.
```

### 5. Versioned artifacts manage dependency correctness

Problem statement artifacts depend on form artifacts.

When a form artifact is superseded, downstream artifacts that depend on the old form can be marked stale.

---

## Thread IDs and multi-turn behavior

A UI application should normally use:

```text
one user-facing workflow session = one thread_id
```

For example:

```python
config = {
    "configurable": {
        "thread_id": "workflow_session_123",
        "user_id": "user_456",
    }
}
```

Use the same `thread_id` when the user is continuing the same workflow. Use a new `thread_id` when the user starts a new independent workflow.

### Sticky routing

If a user is in the middle of filling out a form, the orchestrator should route follow-up responses back to the smart form builder, even if the response looks ambiguous.

Example:

```text
Smart Form Builder: What is the stakeholder?
User: Plant managers
```

The orchestrator should not classify `Plant managers` as a random general message. It should know this is part of the active form workflow.

---

## Direct subagent usage

### Direct Smart Form Builder workflow

```python
from orchestrator_agents.agent_workflows import build_smart_form_builder_agent_graph
from orchestrator_agents.agents.smart_form import DEFAULT_PROBLEM_FORM_SCHEMA

form_graph = build_smart_form_builder_agent_graph()

result = form_graph.invoke(
    {
        "user_message": "I want to fill out the problem discovery form.",
        "user_id": "user_1",
        "thread_id": "form_session_1",
        "form_schema": DEFAULT_PROBLEM_FORM_SCHEMA.model_dump(),
        "form_state": None,
    },
    config={"configurable": {"thread_id": "form_session_1"}},
)

print(result["final_answer"])
form_state = result["form_output"]["updated_form_state"]
```

On the next direct turn:

```python
result = form_graph.invoke(
    {
        "user_message": "Operations managers",
        "user_id": "user_1",
        "thread_id": "form_session_1",
        "form_schema": DEFAULT_PROBLEM_FORM_SCHEMA.model_dump(),
        "form_state": form_state,
    },
    config={"configurable": {"thread_id": "form_session_1"}},
)
```

### Direct Problem Statement workflow

```python
from orchestrator_agents.agent_workflows import build_problem_statement_agent_graph

problem_graph = build_problem_statement_agent_graph(artifact_store=artifact_store)

result = problem_graph.invoke(
    {
        "user_message": "Generate the problem statement.",
        "user_id": "user_1",
        "thread_id": "problem_session_1",
        "form_artifact_id": "artifact_form_v1",
    },
    config={"configurable": {"thread_id": "problem_session_1"}},
)

print(result["final_answer"])
```

---

## Orchestrated subagent usage

The orchestrator converts its own state into each subagent graph's public input contract.

```text
OrchestratorState
  ↓ adapter
SmartFormWorkflowState
  ↓ smart form graph
AgentResult
  ↓ adapter
OrchestratorState update
```

The adapter logic lives in `graph/build.py`.

This design allows each subagent workflow to be invoked directly or through the orchestrator without changing the agent internals.

---

## Artifact dependency handling

The dependency model is based on versioned artifacts.

### Form artifact

```text
artifact_type = smart_form
version = 1
status = current
```

### Problem statement artifact

```text
artifact_type = problem_statement
depends_on = [form artifact v1]
```

### When the form is updated

```text
form_v2 supersedes form_v1
problem_statement_v1 depends_on form_v1
problem_statement_v1 becomes stale
```

The orchestrator asks:

```text
I updated the form. Your current problem statement was generated from the previous form version, so it may no longer be accurate. Would you like me to update the problem statement too?
```

If the user says yes, sticky dependency-resolution routing sends the user to the Problem Statement Agent workflow.

---

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run the CLI demo:

```bash
orchestrator-demo
```

Run tests:

```bash
pytest -q
```

Compile check:

```bash
python -m compileall -q src tests
```

---

## Persistence guidance

This repo uses local/demo storage by default.

For production:

- Use a durable LangGraph checkpointer, such as Postgres or another supported backend.
- Replace JSON artifact/memory stores with durable storage.
- Add authentication/authorization around artifact reads and cross-thread references.
- Add structured logging/OpenTelemetry/LangSmith tracing.
- Add retention policies for artifacts and workflow state.

---

## Graph visualization note

The orchestrator uses `Command(goto=...)` for dynamic routing. Some graph renderers may not show every possible runtime handoff as a static edge.

This is expected.

A graph may visually show nodes that look disconnected even though the orchestrator can route to them at runtime. Type hints and route metadata help document valid destinations.

---

## Testing strategy

The test suite covers:

- deterministic routing
- ambiguous/fallback routing
- artifact and memory separation
- context packaging
- direct smart form behavior
- direct problem statement behavior
- dependency invalidation
- dependency resolution routing
- importability/compilation without requiring LangGraph runtime in non-LangGraph environments

Some LangGraph runtime tests are skipped if LangGraph is not installed.

---

## Production extension points

Useful next upgrades:

1. Replace mocked LLM router with structured-output LLM routing.
2. Add a real route verifier model.
3. Add OpenTelemetry/LangSmith tracing.
4. Add durable artifact storage.
5. Add user/project permissions for cross-thread artifact references.
6. Add human approval before final form submission.
7. Add downstream agents such as solution design, implementation plan, ROI analysis, and executive summary.
8. Add parallel fan-out/fan-in workflows for agents that can process independent subtasks.

---

## Summary

v4 demonstrates the recommended pattern for complex orchestrated agent systems:

```text
Orchestrator = top-level LangGraph control plane
Subagents = reusable LangGraph workflows
Agents = direct-callable and orchestrator-callable
Artifacts = versioned durable outputs
Dependencies = explicit lineage between artifacts
State = active workflow context
Memory = reusable long-term knowledge
```

This lets you build multi-turn, multi-agent workflows that are inspectable, reusable, dependency-aware, and production-oriented.
