from __future__ import annotations

from orchestrator_agents.schemas import AgentSpec


AGENT_REGISTRY: dict[str, AgentSpec] = {
    "research_agent": AgentSpec(
        name="research_agent",
        description="Handles current/source-backed research and latest information.",
        owns_intents=["research", "latest_info", "source_backed_answer"],
        positive_examples=["Find latest docs", "Research recent papers"],
        negative_examples=["Debug my Python error", "Fill out this form"],
        risk_level="medium",
    ),
    "coding_agent": AgentSpec(
        name="coding_agent",
        description="Handles coding, debugging, architecture, APIs, tests, and LangGraph implementation.",
        owns_intents=["coding", "debugging", "software_architecture"],
        positive_examples=["Build a LangGraph workflow", "Fix this Python bug"],
        negative_examples=["Fill out my problem discovery form", "Rewrite this email"],
        risk_level="medium",
    ),
    "writing_agent": AgentSpec(
        name="writing_agent",
        description="Handles writing, rewriting, summaries, emails, tone edits.",
        owns_intents=["writing", "rewriting", "summarization"],
        positive_examples=["Rewrite this email", "Summarize this document"],
        negative_examples=["Build a graph", "Fill out a form"],
        risk_level="low",
    ),
    "smart_form_builder_agent": AgentSpec(
        name="smart_form_builder_agent",
        description="Runs a multi-turn smart form workflow. Collects, validates, reviews, and versions structured form data.",
        owns_intents=["smart_form", "form_fill", "problem_discovery_form", "update_form"],
        positive_examples=["Help me fill out the problem form", "Update the stakeholder in my form"],
        negative_examples=["Generate the final problem statement", "Write Python code"],
        risk_level="medium",
    ),
    "problem_statement_agent": AgentSpec(
        name="problem_statement_agent",
        description="Generates or updates a problem statement from the latest smart form artifact.",
        owns_intents=["problem_statement", "define_problem", "regenerate_problem_statement"],
        positive_examples=["Create the problem statement from my form", "Update the problem statement"],
        negative_examples=["Collect the fields for my form", "Debug my API"],
        required_state_fields=["user_query", "latest_form_artifact_id"],
        risk_level="medium",
    ),
}
