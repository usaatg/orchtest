# LangGraph Orchestrator + Stateless Subagents Example, v2.1

This repo demonstrates a production-oriented pattern for one **orchestrator graph** and three **stateless subagents**:

- `research_agent`
- `coding_agent`
- `writing_agent`

The orchestrator receives the user query, creates a route plan, validates it, applies policy, and hands off to one or more subagents. Subagents are workers: they receive explicit `AgentTask` input and return `AgentResult`. They do not own hidden workflow state.

## What v2 adds

This version implements the 15 production-hardening items from the design review:

1. Cross-thread reference support through `referenced_thread_ids` and `referenced_artifact_ids`.
2. Same-thread artifact usage: large outputs go to `ArtifactStore`; state carries IDs/summaries.
3. Explicit identity model: `thread_id`, `run_id`, `handoff_id`, `task_id`, `agent_id`.
4. Route plans, including `research_agent -> coding_agent` multi-step workflows.
5. Separate verifier step before policy execution.
6. Risk-aware routing thresholds.
7. Golden and adversarial routing tests.
8. Per-subagent context packaging through `build_agent_task`.
9. Separate checkpoint state, artifact storage, and durable memory storage.
10. Stateless subagent contract: `AgentTask -> AgentResult`.
11. Clarification behavior distinct from fallback behavior.
12. UI/session model documentation.
13. Production persistence guidance.
14. Structured observability events.
15. Dynamic graph visualization guidance for `Command(goto=...)`.

## Project structure

```text
src/orchestrator_agents/
  agents/
    base.py
    coding.py
    research.py
    writing.py
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
  observability.py
  cli.py
  registry.py
  schemas.py

tests/
  routing_cases/
    adversarial_routes.json
    golden_routes.json
  test_artifact_memory.py
  test_graph_multiturn.py
  test_routing.py
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Run the demo

```bash
orchestrator-demo
```

The demo sends multiple turns through the same `thread_id`:

```text
workflow_session_demo
```

The same thread ID preserves active workflow context. The artifact store persists full outputs under `.artifacts/`.

## Thread IDs in a UI application

Use one `thread_id` per user-facing workflow/session:

```json
{
  "thread_id": "workflow_session_abc123",
  "user_query": "Build a LangGraph orchestrator"
}
```

Reuse the same `thread_id` for follow-up turns:

```json
{
  "thread_id": "workflow_session_abc123",
  "user_query": "Now add a research step before coding"
}
```

Create a new `thread_id` when the user starts a new independent workflow.

### Referencing old sessions without resuming them

Use a new `thread_id` plus references:

```json
{
  "thread_id": "new_workflow_002",
  "referenced_thread_ids": ["old_research_thread_001"],
  "referenced_artifact_ids": ["artifact_abc123"]
}
```

This imports curated artifact summaries from older work as read-only context. It does **not** load full old thread state, and it does **not** resume or mutate the old thread. Full artifact content remains in `ArtifactStore` and can be retrieved by ID only when a downstream agent truly needs it.

## State vs artifacts vs memory

Use graph state for active workflow control:

```text
selected_agent
route_plan
current_route_step_index
route_history
handoff_history
artifact_ids
short summaries
```

Use `ArtifactStore` for large or reusable generated outputs:

```text
research summaries
coding plans
drafts
reports
backtest outputs
```

Use `MemoryStore` for durable knowledge across threads:

```text
user preferences
project facts
agent-specific reusable facts
```

Production pattern:

```text
full output -> ArtifactStore
state -> artifact_id + short summary
subagent -> retrieve artifact only when needed
```

## Routing control plane

`RoutingService.decide_plan()` runs:

```text
deterministic_route_plan
  ↓ if no match
llm_route_plan
  ↓
verify_route_plan
  ↓
apply_route_plan_policy
```

The router proposes. The policy gate decides.

The LLM router is intentionally mocked so the repo runs without credentials. Replace `llm_route_plan()` with structured output from your model provider:

```python
router = llm.with_structured_output(RoutePlan)
plan = router.invoke([
    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
    {"role": "user", "content": user_query},
])
```

## Route plans

A single-agent route:

```text
orchestrator -> coding_agent -> finalizer
```

A multi-agent route:

```text
orchestrator -> research_agent -> coding_agent -> finalizer
```

Example query:

```text
Find the latest LangGraph handoff docs and build a Python routing example
```

This routes to research first, then coding.

## Clarification vs fallback

Clarification means the system needs more user input:

```text
"Can you help with my agent?" -> clarification_node
```

Fallback means no specialist fits but the request is answerable:

```text
"What is 2 + 2?" -> fallback_agent
```

## Dynamic graph visualization

The graph uses `Command(goto=...)` for runtime handoffs. Some graph renderers may show agent nodes as disconnected or may not draw every possible runtime handoff as a static edge. That can be correct.

The dynamic handoff happens in `route_policy_node` and `next_step_node`.

Use typed `Command` destinations and route history/observability events to make runtime behavior auditable.

## Production persistence guidance

Demo:

```text
InMemorySaver
JsonArtifactStore
JsonMemoryStore
```

Production:

```text
Postgres/Redis/durable checkpointer
S3/blob/document store for artifacts
database/vector store for memory
LangSmith/OpenTelemetry for tracing
```

In-memory checkpointing is not durable across process restarts.

## Run tests

```bash
pytest
```

Tests cover:

- golden routing cases
- adversarial routing cases
- clarification vs fallback
- route plans
- artifact/memory separation
- multi-turn graph behavior when LangGraph is installed

## Design rule

Subagents are stateless by default. The orchestrator owns active thread state. Durable knowledge goes into memory/artifact stores.
