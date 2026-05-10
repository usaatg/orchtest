from __future__ import annotations

from orchestrator_agents.schemas import AgentSpec

AGENT_REGISTRY: dict[str, AgentSpec] = {
    "research_agent": AgentSpec(
        name="research_agent",
        description=(
            "Handles source-backed research, current/latest information, document analysis, "
            "comparison, discovery, and synthesis."
        ),
        owns_intents=["research", "latest_info", "source_backed_answer", "comparison"],
        positive_examples=[
            "Find the latest LangGraph handoff docs",
            "Research recent approaches to multi-agent routing",
            "Compare three papers and summarize the findings",
        ],
        negative_examples=[
            "Write production Python code from an already-known spec",
            "Rewrite this email",
        ],
        risk_level="medium",
    ),
    "coding_agent": AgentSpec(
        name="coding_agent",
        description=(
            "Handles software engineering, architecture, Python, LangGraph, APIs, tests, "
            "debugging, refactoring, and implementation plans."
        ),
        owns_intents=["coding", "debugging", "software_architecture", "langgraph_help"],
        positive_examples=[
            "Build a LangGraph orchestrator",
            "Debug this Python traceback",
            "Create tests for this API client",
        ],
        negative_examples=[
            "Find the latest news",
            "Rewrite this paragraph in a warmer tone",
        ],
        risk_level="medium",
    ),
    "writing_agent": AgentSpec(
        name="writing_agent",
        description=(
            "Handles writing, rewriting, summarization, style/tone edits, emails, outlines, "
            "scripts, and communication polish."
        ),
        owns_intents=["writing", "rewriting", "summarization", "email_draft"],
        positive_examples=[
            "Rewrite this email professionally",
            "Summarize this note",
            "Create an executive-friendly outline",
        ],
        negative_examples=[
            "Debug my LangGraph app",
            "Analyze a trading setup",
        ],
        risk_level="low",
    ),
}
