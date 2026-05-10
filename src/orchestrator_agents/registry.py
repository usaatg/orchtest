from __future__ import annotations

from orchestrator_agents.schemas import AgentSpec

AGENT_REGISTRY: dict[str, AgentSpec] = {
    "research_agent": AgentSpec(
        name="research_agent",
        description=(
            "Handles source-backed research, latest/current information, papers, product/company "
            "comparisons, and evidence gathering for downstream agents."
        ),
        owns_intents=["research", "latest_info", "source_backed_answer", "evidence_gathering"],
        positive_examples=[
            "Find the latest LangGraph handoff docs",
            "Research current Python backtesting libraries",
            "Compare recent papers about agent routing",
        ],
        negative_examples=["Debug this stack trace", "Rewrite this email"],
        risk_level="medium",
    ),
    "coding_agent": AgentSpec(
        name="coding_agent",
        description=(
            "Handles software engineering, Python, LangGraph, LangChain, APIs, tests, "
            "debugging, architecture, and implementation tasks."
        ),
        owns_intents=["coding", "debugging", "software_architecture", "langgraph_help"],
        positive_examples=[
            "Build a LangGraph workflow",
            "Write Python tests",
            "Debug this API error",
        ],
        negative_examples=["Analyze EURUSD", "Rewrite this paragraph"],
        risk_level="medium",
    ),
    "writing_agent": AgentSpec(
        name="writing_agent",
        description="Handles writing, rewriting, summarization, tone edits, emails, and drafts.",
        owns_intents=["writing", "rewriting", "summarization", "email_draft"],
        positive_examples=[
            "Rewrite this email",
            "Summarize this document",
            "Make this sound more executive",
        ],
        negative_examples=["Build production code", "Find latest docs"],
        risk_level="low",
    ),
}
