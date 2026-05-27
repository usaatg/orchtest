# LangGraph Router + Deterministic Subagent Thread IDs

This is a small runnable LangGraph codebase that demonstrates this thread model:

```text
router_thread_id = UUIDv4 generated once per open conversation

smart_form_builder_thread_id = UUIDv5(namespace, f"{router_thread_id}:smart_form_builder")
best_insights_thread_id      = UUIDv5(namespace, f"{router_thread_id}:best_insights")
```

The router has its own checkpoint thread. Each subagent has its own checkpoint thread. As long as the same router thread ID is reused, the same subagent thread IDs are reused.

## Why this pattern?

Use this when your subagents are independently compiled graphs or independently callable services.

```text
Conversation / router thread
  ├── Router graph state
  ├── Smart Form Builder graph state
  └── Best Insights graph state
```

This avoids forcing different graph schemas to share the exact same checkpointer thread.

## Install

```bash
python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

## Run the demo

```bash
python -m router_subagents.demo
```

You should see:

1. A new router thread ID.
2. Deterministic UUIDv5 thread IDs for both subagents.
3. Router calls to each subagent.
4. Subagent state being preserved across repeated calls under the same router thread ID.

## Run tests

```bash
pytest -q
```

## Main files

```text
src/router_subagents/threading.py
    UUID helpers.

src/router_subagents/subagents.py
    Two independently compiled LangGraph subagents.

src/router_subagents/router.py
    Router graph that calls subagents using deterministic derived thread IDs.

src/router_subagents/demo.py
    Runnable demo.

tests/test_threading.py
    Validates deterministic thread IDs.

tests/test_workflow.py
    Validates router/subagent state behavior.
```

## Production notes

This demo uses `InMemorySaver`, which only persists while the Python process is alive. For production, replace it with a durable checkpointer such as Postgres, Redis, or another supported checkpointer. Keep the thread ID strategy the same.
