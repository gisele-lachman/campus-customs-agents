"""Problem 5 checks, run only against scratch copies in data/scratch/.

The working database and output/audit_trail.json are never touched; the script proves it by
comparing checksums before and after. Run: .venv/bin/python tests/test_harness.py [--offline]
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import multiprocessing
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HW5 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HW5))

from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import PythonStdioTransport  # noqa: E402
from pydantic_ai import ModelResponse, ToolCallPart, UsageLimitExceeded  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402

from backend import audit  # noqa: E402
from backend.config import AUDIT_TRAIL, LIMITS, WORKING_DB  # noqa: E402
from backend.models import AGENT_NAMES, TeamDeps  # noqa: E402
from backend import team  # noqa: E402

ORIGINAL = HW5 / "data" / "campus_customs.db"
SCRATCH = HW5 / "data" / "scratch"
STAMP = datetime.now().strftime("%Y%m%dT%H%M%S")
SCRATCH_DB = SCRATCH / f"test_{STAMP}.db"
SCRATCH_AUDIT = SCRATCH / f"audit_test_{STAMP}.json"

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "pass": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def make_scratch_db() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{WORKING_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(SCRATCH_DB)
    src.backup(dst)
    src.close(), dst.close()


def q(sql: str, params=()):
    with contextlib.closing(sqlite3.connect(SCRATCH_DB)) as con:
        return con.execute(sql, params).fetchall()


def client(role: str) -> Client:
    env = {"CAMPUS_CUSTOMS_ROLE": role, "CAMPUS_CUSTOMS_DB": str(SCRATCH_DB), "PATH": "/usr/bin:/bin",
           "FASTMCP_LOG_LEVEL": "WARNING"}
    return Client(PythonStdioTransport(HW5 / "mcp_server" / "server.py", env=env, cwd=str(HW5),
                                       python_cmd=str(HW5 / ".venv" / "bin" / "python")))


async def call(c: Client, tool: str, **args) -> dict:
    res = await c.call_tool(tool, args)
    return res.structured_content if res.structured_content is not None else json.loads(res.content[0].text)


# --------------------------------------------------------------------------- payments


async def test_payments() -> None:
    async with client("agent") as agent_c, client("backend") as back_c:
        prep = await call(agent_c, "prepare_payment", ticket_id=101, kind="invoice", ref_id=501, reason="test")
        check("prepare_payment creates a pending item", prep.get("prepared") and prep["status"] == "pending",
              f"item {prep.get('item_id')}, amount {prep.get('amount')}")
        item = prep["item_id"]
        dup = await call(agent_c, "prepare_payment", ticket_id=101, kind="invoice", ref_id=501, reason="again")
        check("duplicate payment is not prepared twice", dup.get("prepared") is False, dup.get("message", ""))

        before = q("SELECT balance FROM cash_accounts WHERE name='checking'")[0][0]
        r = await call(back_c, "execute_approved_payment", item_id=item)
        check("payment WITHOUT approval is refused", r["paid"] is False, r["message"])
        check("  ...and nothing changed", q("SELECT COUNT(*) FROM payments")[0][0] == 0
              and q("SELECT balance FROM cash_accounts")[0][0] == before)

        r = await call(back_c, "record_human_decision", item_id=item, decision="approve", decided_by="Test Manager")
        check("human approval recorded", r.get("status") == "approved")

        with contextlib.closing(sqlite3.connect(SCRATCH_DB)) as con:
            con.execute("UPDATE cash_accounts SET balance = 500 WHERE name='checking'"); con.commit()
        r = await call(back_c, "execute_approved_payment", item_id=item)
        check("approved payment WITHOUT enough cash is refused", r["paid"] is False, r["message"])
        check("  ...and nothing changed (no negative balance, invoice still open)",
              q("SELECT balance FROM cash_accounts")[0][0] == 500 and q("SELECT COUNT(*) FROM payments")[0][0] == 0
              and q("SELECT status FROM invoices WHERE id=501")[0][0] == "open")
        with contextlib.closing(sqlite3.connect(SCRATCH_DB)) as con:
            con.execute("UPDATE cash_accounts SET balance = ? WHERE name='checking'", (before,)); con.commit()

        r = await call(back_c, "execute_approved_payment", item_id=item)
        pay = q("SELECT kind, ref_id, amount, account, paid_at, approved_by FROM payments")
        check("approved payment with enough cash is paid", r["paid"] is True, json.dumps(r))
        check("  ...payments row written", pay == [("invoice", 501, 840.0, "checking", "2026-08-31", "Test Manager")], str(pay))
        check("  ...cash lowered", q("SELECT balance FROM cash_accounts")[0][0] == before - 840)
        check("  ...invoice marked paid", q("SELECT status FROM invoices WHERE id=501")[0][0] == "paid")
        check("  ...item marked paid", q("SELECT status FROM pending_items WHERE id=?", (item,))[0][0] == "paid")
        r = await call(back_c, "execute_approved_payment", item_id=item)
        check("paying the same item twice is refused", r["paid"] is False, r["message"])

        rent = await call(agent_c, "prepare_payment", ticket_id=102, kind="rent", ref_id=1, reason="test rent")
        await call(back_c, "record_human_decision", item_id=rent["item_id"], decision="approve", decided_by="Test Manager")
        r = await call(back_c, "execute_approved_payment", item_id=rent["item_id"])
        check("rent payment moves lease next_due a month and lowers cash",
              r["paid"] and q("SELECT next_due FROM leases WHERE id=1")[0][0] == "2026-10-02"
              and q("SELECT balance FROM cash_accounts")[0][0] == before - 840 - 2400, r.get("effect", r.get("message")))

        po = await call(agent_c, "prepare_purchase_order", ticket_id=103, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12, reason="test")
        r = await call(back_c, "execute_approved_payment", item_id=po["item_id"])
        check("pay tool refuses a purchase order item", r["paid"] is False, r["message"])
        low = await call(agent_c, "prepare_price_override", ticket_id=103, sku="CC-HOOD-NAVY", qty=20, unit_price=20, reason="test")
        check("price override below cost is refused", low["prepared"] is False, low["message"])


# --------------------------------------------------------------------------- agent access


async def test_agents_cannot_pay() -> None:
    async with client("agent") as c:
        names = {t.name for t in await c.list_tools()}
        check("agent-role MCP server has no approve/pay tools", not names & team.HUMAN_ONLY_TOOLS, ", ".join(sorted(names)))
        try:
            res = await c.call_tool("execute_approved_payment", {"item_id": 1}, raise_on_error=False)
            refused = res.is_error
            detail = res.content[0].text if res.content else ""
        except Exception as exc:  # unknown tool is an MCP error
            refused, detail = True, f"{type(exc).__name__}: {exc}"
        check("calling execute_approved_payment as an agent fails", refused, detail[:160])
    for name in AGENT_NAMES:
        allowed = team.AGENT_TOOLS[name]
        check(f"{name} tool list excludes pay/approve and only uses real tools",
              not allowed & team.HUMAN_ONLY_TOOLS and allowed <= names, ", ".join(sorted(allowed)))
    stamped = None
    try:
        class Ctx:  # minimal stand-in for RunContext
            deps = TeamDeps(ticket="t", agent="accounting", audit_path=SCRATCH_AUDIT)
        await team._stamp_prepared_by(Ctx(), None, "execute_approved_payment", {"item_id": 1})
    except Exception as exc:
        stamped = type(exc).__name__
    check("agent tool-call hook blocks human-only tool names (second guard)", stamped == "ModelRetry", str(stamped))


# --------------------------------------------------------------------------- audit file


def _writer(path: str, n: int, wid: int) -> None:
    for i in range(n):
        audit.append(Path(path), ticket="concurrency", agent=f"writer{wid}", step_type="tool_call", args=f"i={i}")


def test_audit() -> None:
    path = SCRATCH / f"audit_concurrency_{STAMP}.json"
    procs = [multiprocessing.Process(target=_writer, args=(str(path), 25, w)) for w in range(4)]
    [p.start() for p in procs]
    [p.join() for p in procs]
    data = json.loads(path.read_text())
    check("audit: 4 processes x 25 simultaneous appends -> 100 valid entries", len(data) == 100, f"{len(data)} entries")
    key = os.environ.get("PORTKEY_API_KEY", "")
    audit.append(path, ticket="secret", agent="test", step_type="tool_call", args=f"header x-portkey-api-key={key}",
                 result=f"Bearer {key}")
    text = path.read_text()
    check("audit: key never written (redacted)", key and key not in text and "[REDACTED]" in text)
    before = len(json.loads(path.read_text()))
    audit.append(path, ticket="t", agent="test", step_type="tool_call")
    check("audit: append keeps all earlier entries (never wiped)", len(json.loads(path.read_text())) == before + 1)
    try:
        audit.append(HW5 / "data" / "elsewhere.json", ticket="t", agent="x", step_type="error")
        check("audit: refuses paths outside output/ and data/scratch/", False)
    except RuntimeError:
        check("audit: refuses paths outside output/ and data/scratch/", True)


# --------------------------------------------------------------------------- runaway loop (offline)


def _runaway(messages, info: AgentInfo) -> ModelResponse:
    """A misbehaving model: every turn it delegates again, forever."""
    n = sum(1 for m in messages if isinstance(m, ModelResponse))
    target = AGENT_NAMES[(n + 1) % len(AGENT_NAMES)]
    return ModelResponse(parts=[ToolCallPart("ask_agent", {"agent": target, "question": f"loop {n}"})])


def _tool_spammer(messages, info: AgentInfo) -> ModelResponse:
    """A misbehaving model that calls the same MCP tool over and over."""
    return ModelResponse(parts=[ToolCallPart("check_stock", {"sku": "CC-TEE-WHITE", "size": "S"})])


async def test_runaway() -> None:
    for label, fn, agent in (("delegation loop", _runaway, "boss"), ("tool-call loop", _tool_spammer, "inventory")):
        toolset = team.build_mcp_toolset(SCRATCH_DB)
        deps = TeamDeps(ticket=f"TEST-runaway-{label}", agent=agent, audit_path=SCRATCH_AUDIT,
                        mcp_toolset=toolset, check_model=False)
        with contextlib.ExitStack() as stack:
            for name in AGENT_NAMES:
                stack.enter_context(team.get_agent(name).override(model=FunctionModel(fn)))
            stopped = None
            try:
                async with toolset:
                    await asyncio.wait_for(team.run_agent(agent, "go", deps, output_type=team.AgentReport), 120)
            except UsageLimitExceeded as exc:
                stopped = f"{type(exc).__name__}: {exc}"
            except asyncio.TimeoutError:
                stopped = None
        check(f"runaway {label} is stopped by a limit", stopped is not None,
              f"{stopped}; ticket used {deps.budget.model_requests} model requests, {deps.budget.tool_calls} tool calls")
    entries = json.loads(SCRATCH_AUDIT.read_text())
    depth_stops = [e for e in entries if e["ticket"].startswith("TEST-runaway") and e["stop_reason"] and "max_delegation_depth" in e["stop_reason"]]
    max_depth = max((e["depth"] for e in entries if e["ticket"].startswith("TEST-runaway")), default=0)
    check("delegation never went deeper than max_delegation_depth",
          max_depth <= LIMITS.max_delegation_depth and depth_stops, f"max depth seen {max_depth}, depth refusals {len(depth_stops)}")


# --------------------------------------------------------------------------- live model


async def test_live() -> None:
    question = ("Test only, not a real ticket (use ticket_id 0 in your decision): ask the inventory agent how many "
                "CC-HOOD-NAVY size M hoodies are on hand and whether 20 are available. Do not prepare anything. "
                "Report its answer.")
    report = await team.ask("boss", question, "TEST-delegation", db_path=SCRATCH_DB, audit_path=SCRATCH_AUDIT)
    entries = [e for e in json.loads(SCRATCH_AUDIT.read_text()) if e["ticket"] == "TEST-delegation"]
    models = sorted({e["model"] for e in entries if e["model"]})
    check("live: every reply came from the configured model", models and all(audit.model_matches(m) for m in models),
          f"models seen: {models}")
    deleg = [e for e in entries if e["step_type"] == "delegation"]
    inv_tools = [e for e in entries if e["agent"] == "inventory" and e["step_type"] == "tool_call"]
    check("live: boss delegated to inventory and got an answer back",
          any(e["tool_name"] == "ask_agent -> inventory" for e in deleg)
          and any(e["tool_name"] == "ask_agent <- inventory" for e in deleg),
          f"inventory tools used: {[e['tool_name'] for e in inv_tools]}")
    check("live: answer matches the database (8 on hand, short 12)",
          "8" in report.summary and "12" in report.summary, report.summary)
    print("   boss report:", report.model_dump_json()[:600])
    for e in entries:
        print("   ", e["agent"], e["depth"], e["step_type"], e["tool_name"] or "", (e["args"] or "")[:70], "|",
              e["stop_reason"] or "", e["model"] or "")


# --------------------------------------------------------------------------- main


async def main(offline: bool) -> None:
    protected = {"original db": ORIGINAL, "working db": WORKING_DB, "real audit trail": AUDIT_TRAIL}
    before = {k: sha(p) for k, p in protected.items()}
    make_scratch_db()
    print(f"scratch db: {SCRATCH_DB.relative_to(HW5)}; scratch audit: {SCRATCH_AUDIT.relative_to(HW5)}")
    await test_payments()
    await test_agents_cannot_pay()
    test_audit()
    await test_runaway()
    if not offline:
        make_scratch_db()  # fresh copy so payment tests don't affect the live run
        await test_live()
    after = {k: sha(p) for k, p in protected.items()}
    for k in protected:
        check(f"{k} unchanged", before[k] == after[k], f"sha256 {after[k]}")
    passed = sum(r["pass"] for r in results)
    print(f"\n{passed}/{len(results)} checks passed")
    (SCRATCH / f"test_report_{STAMP}.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    asyncio.run(main("--offline" in sys.argv))
