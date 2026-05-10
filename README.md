# LangGraph Orchestrator + Stateless Subagents Example

This repo shows a production-oriented pattern for one orchestrator agent and three stateless subagents:

- `research_agent`
- `coding_agent`
- `writing_agent`

The orchestrator owns the user-facing workflow thread. Subagents are stateless workers: they receive explicit task/context, return structured results, and do not own hidden conversation state.

## Why this design

Core ideas:

1. **One thread per user-facing workflow session**
   - The UI should create or reuse one `thread_id` for the active workflow/session.
   - Follow-up turns use the same `thread_id`.

2. **Subagents are stateless by default**
   - They do not maintain private mutable state.
   - They receive `AgentTask` and return `AgentResult`.

3. **Routing is a reusable subsystem**
   - Deterministic high-precision rules
   - Optional LLM structured router boundary
   - Route verifier
   - Deterministic route policy gate

4. **State is small; artifacts are stored externally**
   - Graph state keeps artifact IDs and short control data.
   - Full research summaries, code plans, drafts, and large outputs go into an artifact store.

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
    state.py
  routing/
    deterministic.py
    llm_router.py
    policy.py
    service.py
    verifier.py
  storage/
    artifact_store.py
  cli.py
  registry.py
  schemas.py

tests/
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

The demo sends three turns through the same `thread_id`:

1. Coding request
2. Research request
3. Writing request

The checkpointer preserves multi-turn state. The artifact store persists full outputs under `.artifacts/`.

## Run tests

```bash
pytest
```

## How routing works

`RoutingService.decide()` performs:

```text
deterministic_route
  ↓ if no match
llm_route
  ↓
verify_route
  ↓
apply_route_policy
```

The LLM router is intentionally mocked so the repo runs without provider credentials. Replace `llm_route()` with your model provider using structured output:

```python
router = llm.with_structured_output(RouteDecision)
decision = router.invoke([
    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
    {"role": "user", "content": user_query},
])
```

## Thread ID guidance

Use the same `thread_id` for the same user-facing workflow/session:

```python
config = {"configurable": {"thread_id": "workflow_session_123"}}
```

Create a new `thread_id` when the user starts a new independent workflow. If the new workflow should reference prior work, store the prior work as artifacts and pass artifact IDs into the new workflow rather than reusing the old checkpoint state directly.

## Production upgrades

For production, replace:

- `InMemorySaver` with a persistent checkpointer such as Postgres/Redis/SQLite depending on your deployment.
- `JsonArtifactStore` with Postgres, S3/blob storage, or a document store.
- Mock `llm_route()` with a real structured-output LLM router.
- Mock subagents with real specialist agents/tools.
- Add LangSmith/OpenTelemetry tracing.
- Add golden routing tests and adversarial routing tests in CI.

## Important design rule

The router proposes. The policy gate decides.

Do not let an LLM route directly to a subagent without deterministic policy checks, confidence thresholds, ambiguity checks, and verification.
