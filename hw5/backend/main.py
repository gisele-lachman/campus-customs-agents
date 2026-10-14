"""Campus Customs backend (FastAPI).

Start from inside backend/:  uvicorn main:app --reload --port 8000

- Agent runs use the MCP server in its "agent" role (backend/team.py); they can only prepare items.
- Approve/reject are the only routes that start the MCP server in its "backend" role, which has the
  human-only tools record_human_decision and execute_approved_payment. Only approving a payment moves cash.
- Every route reads and writes config.DB_PATH (the working copy) and config.AUDIT_TRAIL. Tests point
  both at data/scratch/ with CAMPUS_CUSTOMS_DB and CAMPUS_CUSTOMS_AUDIT.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HW5_DIR = Path(__file__).resolve().parent.parent
if str(HW5_DIR) not in sys.path:  # lets "uvicorn main:app" run from inside backend/
    sys.path.insert(0, str(HW5_DIR))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import PythonStdioTransport  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend import audit, team  # noqa: E402
from backend.config import AUDIT_TRAIL, DB_PATH, MCP_SERVER_SCRIPT, ORIGINAL_DB, PYTHON  # noqa: E402

ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
BLOCKING_TYPES = ("payment", "purchase_order")  # the items that must be decided before a ticket resolves
DEFAULT_EVENT_LIMIT = 200

RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'finished', 'failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    decision TEXT,
    error TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
)
"""

app = FastAPI(title="Campus Customs backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def refuse_other_origins(request: Request, call_next):
    """Browsers from any other origin are refused outright (not just denied the CORS header)."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": f"Origin {origin} is not allowed."}, status_code=403)
    return await call_next(request)


# --------------------------------------------------------------------------- helpers


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db(write: bool = False) -> sqlite3.Connection:
    if DB_PATH.resolve() == ORIGINAL_DB.resolve():
        raise RuntimeError("Refusing to use the original database.")
    if not DB_PATH.exists():
        raise HTTPException(500, f"Database not found: {DB_PATH.name}")
    mode = "rw" if write else "ro"
    con = sqlite3.connect(f"file:{DB_PATH}?mode={mode}", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    if write:
        con.execute(RUNS_SCHEMA)
    return con


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _latest_run(con: sqlite3.Connection, ticket_id: int) -> dict | None:
    if not _has_table(con, "ticket_runs"):
        return None
    row = con.execute("SELECT * FROM ticket_runs WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (ticket_id,)).fetchone()
    return _run_dict(row) if row else None


def _run_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["decision"] = json.loads(d["decision"]) if d.get("decision") else None
    return d


def _undecided_items(con: sqlite3.Connection, ticket_id: int) -> list[dict]:
    """Payments and purchase orders still waiting: pending, or approved but not yet paid (cash was short)."""
    if not _has_table(con, "pending_items"):
        return []
    rows = con.execute(
        "SELECT id, item_type, status, amount FROM pending_items WHERE ticket_id=? AND item_type IN (?, ?) "
        "AND (status='pending' OR (item_type='payment' AND status='approved'))",
        (ticket_id, *BLOCKING_TYPES),
    ).fetchall()
    return [dict(r) for r in rows]


def _maybe_resolve(ticket_id: int) -> bool:
    """Resolve the ticket if its last run finished and none of its payments/purchases are undecided."""
    with closing(_db(write=True)) as con:
        run = _latest_run(con, ticket_id)
        if run is None or run["status"] != "finished" or _undecided_items(con, ticket_id):
            return False
        changed = con.execute("UPDATE tickets SET status='resolved' WHERE id=? AND status!='resolved'", (ticket_id,)).rowcount
        con.commit()
    if not changed:  # already resolved: don't log it again
        return False
    audit.append(AUDIT_TRAIL, ticket=str(ticket_id), agent="backend", step_type="human_decision",
                 result="ticket resolved: run finished and no payment or purchase is waiting")
    return True


def _backend_mcp() -> Client:
    """The MCP server in its backend role: the only place the human-only tools exist."""
    env = {"CAMPUS_CUSTOMS_ROLE": "backend", "CAMPUS_CUSTOMS_DB": str(DB_PATH), "PATH": "/usr/bin:/bin",
           "FASTMCP_LOG_LEVEL": "WARNING"}
    return Client(PythonStdioTransport(MCP_SERVER_SCRIPT, env=env, cwd=str(HW5_DIR), python_cmd=str(PYTHON)))


async def _call(client: Client, tool: str, **args) -> dict:
    res = await client.call_tool(tool, args)
    return res.structured_content if res.structured_content is not None else json.loads(res.content[0].text)


# --------------------------------------------------------------------------- run state (one run at a time)

_run_lock = asyncio.Lock()
_current: dict[str, Any] = {}  # {"run_id", "ticket_id", "task"} while a run is active


def _run_active() -> bool:
    task = _current.get("task")
    return task is not None and not task.done()


async def _do_run(run_id: int, ticket_id: int) -> None:
    status, decision, error = "failed", None, None
    try:
        result = await team.run_ticket(ticket_id, db_path=DB_PATH, audit_path=AUDIT_TRAIL)
        status, decision = "finished", result.model_dump_json()
    except Exception as exc:  # limits, model substitution, network: the run fails, the ticket stays open
        error = audit.short(f"{type(exc).__name__}: {exc}", 500)
    with closing(_db(write=True)) as con:
        con.execute("UPDATE ticket_runs SET status=?, finished_at=?, decision=?, error=? WHERE id=?",
                    (status, _now(), decision, error, run_id))
        con.commit()
    if status == "finished":
        _maybe_resolve(ticket_id)


# --------------------------------------------------------------------------- routes


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "database": str(DB_PATH.relative_to(HW5_DIR)), "audit_trail": str(AUDIT_TRAIL.relative_to(HW5_DIR)),
            "run_active": _run_active()}


@app.get("/api/tickets")
def list_tickets() -> list[dict]:
    with closing(_db()) as con:
        rows = con.execute("SELECT id, type, requester, subject, status FROM tickets ORDER BY id").fetchall()
        out = []
        for r in rows:
            run = _latest_run(con, r["id"])
            out.append(dict(r) | {
                "last_run": {k: run[k] for k in ("id", "status", "started_at", "finished_at")} if run else None,
                "waiting_on_human": len(_undecided_items(con, r["id"])),
            })
    return out


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> dict:
    async with _run_lock:
        if _run_active():
            raise HTTPException(409, f"Run {_current['run_id']} on ticket {_current['ticket_id']} is still going. One run at a time.")
        with closing(_db(write=True)) as con:
            ticket = con.execute("SELECT id, status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if ticket is None:
                raise HTTPException(404, f"No ticket {ticket_id}.")
            if ticket["status"] == "resolved":
                raise HTTPException(409, f"Ticket {ticket_id} is resolved; it can't be run again.")
            last = _latest_run(con, ticket_id)
            if last and last["status"] == "finished":
                raise HTTPException(409, f"Ticket {ticket_id} already has a finished run ({last['id']}); "
                                         "it's waiting on human approvals, not another run.")
            cur = con.execute("INSERT INTO ticket_runs (ticket_id, status, started_at) VALUES (?, 'running', ?)",
                              (ticket_id, _now()))
            con.commit()
            run_id = cur.lastrowid
        task = asyncio.create_task(_do_run(run_id, ticket_id))
        _current.update(run_id=run_id, ticket_id=ticket_id, task=task)
    return {"run_id": run_id, "ticket_id": ticket_id, "status": "running",
            "poll": f"/api/runs/{run_id}", "events": f"/api/events?ticket={ticket_id}"}


@app.get("/api/runs/{run_id}")
def run_status(run_id: int) -> dict:
    with closing(_db()) as con:
        row = con.execute("SELECT * FROM ticket_runs WHERE id=?", (run_id,)).fetchone() if _has_table(con, "ticket_runs") else None
        if row is None:
            raise HTTPException(404, f"No run {run_id}.")
        run = _run_dict(row)
        ticket_status = con.execute("SELECT status FROM tickets WHERE id=?", (run["ticket_id"],)).fetchone()["status"]
    return run | {"ticket_status": ticket_status}


@app.get("/api/runs")
def runs() -> dict:
    """All runs since the last reset, plus which one (if any) is active."""
    with closing(_db()) as con:
        rows = con.execute("SELECT * FROM ticket_runs ORDER BY id").fetchall() if _has_table(con, "ticket_runs") else []
    return {"active_run_id": _current.get("run_id") if _run_active() else None, "runs": [_run_dict(r) for r in rows]}


@app.get("/api/events")
def events(ticket: str | None = None, limit: int = DEFAULT_EVENT_LIMIT) -> dict:
    """Audit-trail events since the last reset marker, oldest first / newest last."""
    entries: list = []
    if AUDIT_TRAIL.exists() and AUDIT_TRAIL.stat().st_size:
        try:
            entries = json.loads(AUDIT_TRAIL.read_text())
        except ValueError:
            raise HTTPException(503, "Audit trail is being written; try again.")
    last_reset = max((i for i, e in enumerate(entries) if e.get("step_type") == "reset"), default=-1)
    since = entries[last_reset + 1:]
    if ticket is not None:
        since = [e for e in since if e.get("ticket") == ticket]
    limit = max(1, min(limit, 2000))
    return {"since_reset_at": entries[last_reset]["time"] if last_reset >= 0 else None,
            "total": len(since), "events": since[-limit:]}


@app.get("/api/pending")
def pending(ticket: int | None = None, status: str | None = None) -> list[dict]:
    with closing(_db()) as con:
        if not _has_table(con, "pending_items"):
            return []
        sql, params = "SELECT * FROM pending_items WHERE 1=1", []
        if ticket is not None:
            sql, params = sql + " AND ticket_id=?", params + [ticket]
        if status is not None:
            sql, params = sql + " AND status=?", params + [status]
        return [dict(r) for r in con.execute(sql + " ORDER BY id", params)]


class Decision(BaseModel):
    by: str = Field(default="Store manager", min_length=1, max_length=80, description="The human deciding.")


def _item_or_404(item_id: int) -> dict:
    with closing(_db()) as con:
        row = con.execute("SELECT * FROM pending_items WHERE id=?", (item_id,)).fetchone() if _has_table(con, "pending_items") else None
    if row is None:
        raise HTTPException(404, f"No pending item {item_id}.")
    return dict(row)


@app.post("/api/pending/{item_id}/approve")
async def approve(item_id: int, body: Decision | None = None) -> dict:
    by = (body or Decision()).by.strip()
    item = _item_or_404(item_id)
    retry_unpaid = item["item_type"] == "payment" and item["status"] == "approved"
    if item["status"] != "pending" and not retry_unpaid:
        raise HTTPException(409, f"Item {item_id} is already '{item['status']}'.")

    async with _backend_mcp() as mcp:
        if item["item_type"] == "payment":
            cash = await _call(mcp, "get_cash_balance")
            checking = next((a["balance"] for a in cash.get("accounts", []) if a["name"] == "checking"), None)
            if checking is None or checking < item["amount"]:
                audit.append(AUDIT_TRAIL, ticket=str(item["ticket_id"]), agent="backend", step_type="human_decision",
                             tool_name="approve", args=f"item {item_id} by {by}",
                             result=f"refused: checking ${checking} < ${item['amount']}")
                held = "no checking account" if checking is None else f"checking holds ${checking:,.2f}"
                raise HTTPException(409, f"Not enough cash: {held} but item {item_id} needs "
                                         f"${item['amount']:,.2f}. Nothing was approved or paid; the item is still "
                                         f"'{item['status']}'.")
        if not retry_unpaid:
            decided = await _call(mcp, "record_human_decision", item_id=item_id, decision="approve", decided_by=by)
            if not decided.get("ok"):
                raise HTTPException(409, decided.get("message", "Could not record the approval."))
        paid = None
        if item["item_type"] == "payment":
            paid = await _call(mcp, "execute_approved_payment", item_id=item_id)

    audit.append(AUDIT_TRAIL, ticket=str(item["ticket_id"]), agent="backend", step_type="human_decision",
                 tool_name="approve", args=f"item {item_id} ({item['item_type']}) by {by}",
                 result=audit.short(paid if paid else "approved"))
    if paid is not None and not paid.get("paid"):
        raise HTTPException(409, f"Approved, but the payment was refused: {paid.get('message')} "
                                 "The item stays approved and unpaid; approve again later or reject it.")
    resolved = _maybe_resolve(item["ticket_id"]) if item["ticket_id"] else False
    return {"item_id": item_id, "status": "paid" if paid else "approved", "payment": paid,
            "ticket_id": item["ticket_id"], "ticket_resolved": resolved}


@app.post("/api/pending/{item_id}/reject")
async def reject(item_id: int, body: Decision | None = None) -> dict:
    by = (body or Decision()).by.strip()
    item = _item_or_404(item_id)
    async with _backend_mcp() as mcp:
        decided = await _call(mcp, "record_human_decision", item_id=item_id, decision="reject", decided_by=by)
    if not decided.get("ok"):
        raise HTTPException(409, decided.get("message", "Could not record the rejection."))
    audit.append(AUDIT_TRAIL, ticket=str(item["ticket_id"]), agent="backend", step_type="human_decision",
                 tool_name="reject", args=f"item {item_id} ({item['item_type']}) by {by}", result="rejected")
    resolved = _maybe_resolve(item["ticket_id"]) if item["ticket_id"] else False
    return {"item_id": item_id, "status": "rejected", "ticket_id": item["ticket_id"], "ticket_resolved": resolved}


@app.get("/api/cash")
def cash() -> dict:
    with closing(_db()) as con:
        row = con.execute("SELECT name, balance, date FROM cash_accounts WHERE name='checking'").fetchone()
    if row is None:
        raise HTTPException(404, "No checking account in cash_accounts.")
    return dict(row)


@app.post("/api/reset")
async def reset() -> dict:
    async with _run_lock:
        if _run_active():
            raise HTTPException(409, "A run is in progress; reset is refused until it finishes.")
        if DB_PATH.resolve() == ORIGINAL_DB.resolve():
            raise HTTPException(500, "Refusing to overwrite the original database.")
        # Byte-for-byte copy: the original is only read, into a temp file that atomically replaces the working copy.
        tmp = DB_PATH.with_name(f".{DB_PATH.name}.resetting")
        shutil.copyfile(ORIGINAL_DB, tmp)
        os.replace(tmp, DB_PATH)
        _current.clear()
        audit.append(AUDIT_TRAIL, ticket="-", agent="backend", step_type="reset",
                     result=f"{DB_PATH.name} restored from {ORIGINAL_DB.name}; events before this are hidden, not deleted")
    return {"ok": True, "database": DB_PATH.name, "restored_from": ORIGINAL_DB.name}
