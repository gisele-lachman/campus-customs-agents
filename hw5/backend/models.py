"""Data types shared by the agent team."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

StepType = Literal["model_reply", "tool_call", "delegation", "run_start", "run_end", "limit_stop", "error", "reset",
                   "human_decision"]


class Fact(BaseModel):
    """One fact an agent learned, with the tool it came from so a human can check it."""

    statement: str = Field(description="The fact, with numbers, e.g. 'CC-TEE-WHITE size S: 0 on hand'.")
    source_tool: str = Field(description="The MCP tool or agent that supplied it, e.g. 'check_stock'.")


class AgentReport(BaseModel):
    """What a specialist agent hands back to whoever asked it."""

    agent: AgentName
    answer: str = Field(description="Short, direct answer to the question asked.")
    facts: list[Fact] = Field(default_factory=list, description="Facts used, each tied to its tool.")
    prepared_item_ids: list[int] = Field(default_factory=list, description="pending_items ids this agent created.")
    blockers: list[str] = Field(default_factory=list, description="Anything stopping progress, e.g. a blocked vendor.")
    needs_human: bool = Field(description="True if a human must approve or decide something.")


class TicketDecision(BaseModel):
    """The Boss's final call on a ticket."""

    ticket_id: int
    decision: Literal["proceed_pending_approval", "blocked", "decline", "needs_more_info"]
    summary: str = Field(description="Two to four sentences a store manager can act on.")
    facts: list[Fact] = Field(default_factory=list)
    prepared_item_ids: list[int] = Field(default_factory=list, description="Every pending item prepared for this ticket.")
    human_actions_needed: list[str] = Field(default_factory=list, description="Exactly what a human must approve or do.")
    agents_consulted: list[AgentName] = Field(default_factory=list)


class AuditEntry(BaseModel):
    """One step of an agent loop, as written to output/audit_trail.json."""

    time: str
    ticket: str
    agent: str
    step_type: StepType
    tool_name: str | None = None
    args: str | None = None
    result: str | None = None
    stop_reason: str | None = None
    model: str | None = None
    depth: int = 0


@dataclass
class TicketBudget:
    """Counters shared by every agent working on one ticket."""

    model_requests: int = 0
    tool_calls: int = 0


@dataclass
class TeamDeps:
    """Run context handed to every agent. Each delegation makes a copy one level deeper."""

    ticket: str  # ticket id as text, or a test label
    agent: AgentName
    audit_path: Path
    depth: int = 0
    chain: tuple[AgentName, ...] = ()
    budget: TicketBudget = field(default_factory=TicketBudget)
    check_model: bool = True  # verify every reply came from the configured model
    mcp_toolset: Any = None  # one MCP server connection shared by every agent on the ticket

    def for_agent(self, agent: AgentName) -> "TeamDeps":
        return replace(self, agent=agent, depth=self.depth + 1, chain=self.chain + (self.agent,))
