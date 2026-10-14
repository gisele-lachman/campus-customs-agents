"""The Campus Customs agent team: Boss, Inventory, Accounting, Facilities, Customer Service.

Every agent gets two things only:
- the shop's MCP server (mcp_server/server.py, started in its "agent" role, so the tools that
  approve or pay do not exist in that process), filtered to the tools its job needs;
- ask_agent, which delegates a question to any other agent and returns that agent's report.

Every step of every agent loop is appended to the audit trail. Limits live in config.LIMITS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from openai import AsyncOpenAI
from pydantic_ai import (
    Agent,
    ModelRetry,
    RetryPromptPart,
    RunContext,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from . import audit
from .config import (
    AUDIT_TRAIL,
    HW5_DIR,
    LIMITS,
    MCP_SERVER_SCRIPT,
    MODEL_NAME,
    PORTKEY_BASE_URL,
    PROMPTS_DIR,
    PYTHON,
    portkey_api_key,
)
from .models import AGENT_NAMES, AgentName, AgentReport, TeamDeps, TicketDecision

# MCP tools each agent may see (least privilege). Prepare tools only create pending items for a human.
AGENT_TOOLS: dict[AgentName, frozenset[str]] = {
    "boss": frozenset({"list_tickets", "get_ticket", "list_pending_items", "get_cash_balance"}),
    "inventory": frozenset({"get_ticket", "check_stock", "list_vendors", "check_vendor_invoice", "get_pricing_margin"}),
    "accounting": frozenset({
        "get_ticket", "get_cash_balance", "check_vendor_invoice", "check_rent_status", "get_pricing_margin",
        "list_vendors", "list_pending_items", "prepare_payment", "prepare_purchase_order", "prepare_price_override",
    }),
    "facilities": frozenset({"get_ticket", "check_rent_status", "get_cash_balance", "list_pending_items"}),
    "customer_service": frozenset({
        "get_ticket", "check_stock", "get_pricing_margin", "list_pending_items", "prepare_customer_message",
    }),
}
# Never offered to an agent, even if a server process were started in the wrong role.
HUMAN_ONLY_TOOLS = frozenset({"record_human_decision", "execute_approved_payment"})
PREPARE_TOOLS = frozenset({"prepare_payment", "prepare_purchase_order", "prepare_price_override", "prepare_customer_message"})


class TicketBudgetExceeded(UsageLimitExceeded):
    """A per-ticket limit was hit. Stops every agent on the ticket, not just the current one."""


class ModelSubstituted(RuntimeError):
    """A reply came from a model other than MODEL_NAME (Portkey can swap unknown names silently)."""


# --------------------------------------------------------------------------- model + MCP


def build_model() -> OpenAIResponsesModel:
    # Responses API: Portkey's chat-completions route rejects function tools for this model.
    key = portkey_api_key()
    client = AsyncOpenAI(base_url=PORTKEY_BASE_URL, api_key=key, default_headers={"x-portkey-api-key": key},
                         timeout=LIMITS.request_timeout_seconds, max_retries=LIMITS.request_retries)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


async def _stamp_prepared_by(ctx: RunContext[TeamDeps], call_tool, name: str, args: dict[str, Any]):
    """The harness, not the model, says which agent prepared an item."""
    if name in HUMAN_ONLY_TOOLS:
        raise ModelRetry(f"{name} is for humans only and is not available to agents.")
    if name in PREPARE_TOOLS:
        args = {**args, "prepared_by": ctx.deps.agent}
    return await call_tool(name, args)


def build_mcp_toolset(db_path: Path | None = None) -> MCPToolset:
    """Start the MCP server over stdio in its agent role. db_path is only for scratch-copy tests."""
    env = {"CAMPUS_CUSTOMS_ROLE": "agent", "PATH": "/usr/bin:/bin", "FASTMCP_LOG_LEVEL": "WARNING"}
    if db_path is not None:
        env["CAMPUS_CUSTOMS_DB"] = str(db_path)
    transport = PythonStdioTransport(MCP_SERVER_SCRIPT, env=env, cwd=str(HW5_DIR), python_cmd=str(PYTHON))
    return MCPToolset(Client(transport), process_tool_call=_stamp_prepared_by, max_retries=1)


# --------------------------------------------------------------------------- agents


def _load_prompt(name: AgentName) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


AGENT_ROSTER = (
    "boss: triage, final call. inventory: stock by sku/size, shortfalls, which vendor can restock, blocked or not, "
    "lead time. accounting: cash, invoices, margins; PREPARES payments, purchase orders and price overrides for "
    "human approval. facilities: leases and rent. customer_service: DRAFTS messages to customers."
)


async def ask_agent(ctx: RunContext[TeamDeps], agent: AgentName, question: str) -> dict:
    """Delegate a question to another Campus Customs agent and get its report back.

    Agents: boss (triage, final call); inventory (stock, shortfalls, restock vendor, lead time);
    accounting (cash, invoices, margins, prepares payments/purchase orders/price overrides);
    facilities (leases, rent); customer_service (drafts customer messages).
    Ask one specific question and include the ticket id and the facts the other agent needs.
    """
    deps = ctx.deps
    if agent == deps.agent:
        return {"delegated": False, "message": "You cannot delegate to yourself. Answer it with your own tools."}
    if agent in deps.chain:
        return {"delegated": False,
                "message": f"{agent} is already waiting on you in this chain ({' -> '.join(deps.chain + (deps.agent,))}). "
                           "Answer with what you have instead of asking it back."}
    if deps.depth >= LIMITS.max_delegation_depth:
        audit.append(deps.audit_path, ticket=deps.ticket, agent=deps.agent, step_type="limit_stop",
                     tool_name="ask_agent", args=f"to {agent}: {question}",
                     stop_reason=f"max_delegation_depth={LIMITS.max_delegation_depth}", depth=deps.depth)
        return {"delegated": False,
                "message": f"Delegation depth limit ({LIMITS.max_delegation_depth}) reached. Answer with what you have."}

    child = deps.for_agent(agent)
    audit.append(deps.audit_path, ticket=deps.ticket, agent=deps.agent, step_type="delegation",
                 tool_name=f"ask_agent -> {agent}", args=question, depth=deps.depth)
    try:
        report = await run_agent(agent, question, child)
    except TicketBudgetExceeded:
        raise
    except UsageLimitExceeded as exc:
        report_dict = {"delegated": True, "agent": agent, "stopped": True, "message": f"{agent} hit a limit: {exc}"}
    else:
        report_dict = {"delegated": True, **report.model_dump()}
    audit.append(deps.audit_path, ticket=deps.ticket, agent=deps.agent, step_type="delegation",
                 tool_name=f"ask_agent <- {agent}", result=json.dumps(report_dict, default=str), depth=deps.depth)
    return report_dict


def _dynamic_context(ctx: RunContext[TeamDeps]) -> str:
    d = ctx.deps
    asked_by = d.chain[-1] if d.chain else "the shop's ticket runner"
    return (
        f"Run context: ticket {d.ticket}. You were asked by {asked_by}. Delegation depth {d.depth} of "
        f"{LIMITS.max_delegation_depth}"
        + (" (you can no longer delegate; answer with your own tools)." if d.depth >= LIMITS.max_delegation_depth else ".")
        + f" Budget for this run: {LIMITS.requests_per_agent_run} model requests and {LIMITS.tool_calls_per_agent_run} "
        f"tool calls. Agents on this team: {AGENT_ROSTER}"
    )


def _make_agent(name: AgentName, model: OpenAIResponsesModel) -> Agent[TeamDeps, Any]:
    agent = Agent(
        model,
        name=name,
        deps_type=TeamDeps,
        output_type=TicketDecision if name == "boss" else AgentReport,
        instructions=[_load_prompt(name), _dynamic_context],
        tools=[ask_agent],
        model_settings=OpenAIResponsesModelSettings(
            max_tokens=LIMITS.max_output_tokens_per_reply, openai_reasoning_effort=LIMITS.reasoning_effort
        ),
        retries=1,
    )
    return agent


_AGENTS: dict[AgentName, Agent] = {}


def get_agent(name: AgentName) -> Agent[TeamDeps, Any]:
    if name not in _AGENTS:
        model = build_model()
        for n in AGENT_NAMES:
            _AGENTS[n] = _make_agent(n, model)
    return _AGENTS[name]


# --------------------------------------------------------------------------- the audited agent loop


def _check_ticket_budget(deps: TeamDeps) -> None:
    b = deps.budget
    if b.model_requests > LIMITS.requests_per_ticket:
        raise TicketBudgetExceeded(f"requests_per_ticket={LIMITS.requests_per_ticket} exceeded")
    if b.tool_calls > LIMITS.tool_calls_per_ticket:
        raise TicketBudgetExceeded(f"tool_calls_per_ticket={LIMITS.tool_calls_per_ticket} exceeded")


async def run_agent(name: AgentName, prompt: str, deps: TeamDeps, output_type: Any = None) -> Any:
    """Run one agent with its filtered MCP tools, logging every step. Returns the agent's output."""
    if deps.mcp_toolset is None:
        raise RuntimeError("TeamDeps.mcp_toolset is not set; use run_ticket() or ask().")
    allowed = AGENT_TOOLS[name] - HUMAN_ONLY_TOOLS
    tools = deps.mcp_toolset.filtered(lambda ctx, td: td.name in allowed)
    limits = UsageLimits(
        request_limit=LIMITS.requests_per_agent_run,
        tool_calls_limit=LIMITS.tool_calls_per_agent_run,
        output_tokens_limit=LIMITS.output_tokens_per_agent_run,
    )
    log = lambda **kw: audit.append(deps.audit_path, ticket=deps.ticket, agent=name, depth=deps.depth, **kw)  # noqa: E731
    pending_calls: dict[str, ToolCallPart] = {}

    log(step_type="run_start", args=prompt)
    try:
        async with get_agent(name).iter(prompt, deps=deps, usage_limits=limits, toolsets=[tools],
                                        output_type=output_type) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    for part in node.request.parts:
                        if isinstance(part, (ToolReturnPart, RetryPromptPart)) and part.tool_name:
                            call = pending_calls.pop(part.tool_call_id, None)
                            if part.tool_name == "final_result":
                                continue
                            log(step_type="tool_call", tool_name=part.tool_name,
                                args=audit.short(call.args if call else None),
                                result=audit.short(part.content),
                                stop_reason="retry" if isinstance(part, RetryPromptPart) else None)
                    deps.budget.model_requests += 1
                    _check_ticket_budget(deps)
                elif Agent.is_call_tools_node(node):
                    resp = node.model_response
                    calls = [p for p in resp.parts if isinstance(p, ToolCallPart)]
                    text = " ".join(p.content for p in resp.parts if isinstance(p, TextPart))
                    is_final = any(c.tool_name == "final_result" for c in calls)
                    log(step_type="model_reply", model=resp.model_name,
                        args=audit.short(", ".join(c.tool_name for c in calls)) or None,
                        result=audit.short(text) if text else None,
                        stop_reason="final_output" if is_final else (resp.finish_reason or "unknown"))
                    if deps.check_model and not audit.model_matches(resp.model_name):
                        raise ModelSubstituted(f"Expected {MODEL_NAME}, got {resp.model_name!r}")
                    for c in calls:
                        if c.tool_name != "final_result":
                            pending_calls[c.tool_call_id] = c
                            deps.budget.tool_calls += 1
                    _check_ticket_budget(deps)
            output = run.result.output
    except UsageLimitExceeded as exc:
        log(step_type="limit_stop", stop_reason=f"{type(exc).__name__}: {exc}")
        raise
    except Exception as exc:
        log(step_type="error", stop_reason=audit.short(f"{type(exc).__name__}: {exc}"))
        raise
    log(step_type="run_end", result=audit.short(output.model_dump() if hasattr(output, "model_dump") else output),
        stop_reason="final_output")
    return output


# --------------------------------------------------------------------------- entry points


async def ask(agent: AgentName, question: str, ticket: str, *, db_path: Path | None = None,
              audit_path: Path = AUDIT_TRAIL, check_model: bool = True) -> AgentReport | TicketDecision:
    """Ask any one agent a question (used by tests and, later, the backend).

    Each agent answers in its own output type (the Boss in TicketDecision); forcing the Boss into
    AgentReport contradicts its prompt and made the model reason until it hit the token cap.
    """
    toolset = build_mcp_toolset(db_path)
    deps = TeamDeps(ticket=ticket, agent=agent, audit_path=audit_path, mcp_toolset=toolset, check_model=check_model)
    async with toolset:
        return await run_agent(agent, question, deps)


async def run_ticket(ticket_id: int, *, db_path: Path | None = None, audit_path: Path = AUDIT_TRAIL) -> TicketDecision:
    """Have the Boss work one ticket end to end. Everything that moves money stays pending for a human."""
    toolset = build_mcp_toolset(db_path)
    deps = TeamDeps(ticket=str(ticket_id), agent="boss", audit_path=audit_path, mcp_toolset=toolset)
    async with toolset:
        return await run_agent(
            "boss",
            f"Work ticket {ticket_id}. Read it with get_ticket, bring in the right agents, make sure every needed "
            f"payment, purchase order, price override and customer draft is prepared as a pending item, then give "
            f"your final call.",
            deps,
        )
