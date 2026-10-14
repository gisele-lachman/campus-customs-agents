"""Problem 7 route checks against a backend started on scratch files.

The backend under test must be started with CAMPUS_CUSTOMS_DB=data/scratch/api_test.db and
CAMPUS_CUSTOMS_AUDIT=data/scratch/api_audit.json. Run: .venv/bin/python tests/test_api.py [base_url]
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

import httpx2 as httpx
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

HW5 = Path(__file__).resolve().parent.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
SCRATCH_DB = HW5 / "data" / "scratch" / "api_test.db"
SCRATCH_AUDIT = HW5 / "data" / "scratch" / "api_audit.json"
ORIGINAL = HW5 / "data" / "campus_customs.db"
GOOD_ORIGIN = "http://localhost:5173"
BAD_ORIGIN = "http://evil.example.com"

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "pass": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""), flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sql(q: str, params=()):
    with closing(sqlite3.connect(SCRATCH_DB)) as con:
        rows = con.execute(q, params).fetchall()
        con.commit()
        return rows


def prepare_po_via_agent_role() -> dict:
    """Make a pending purchase order the way an agent would (agent-role MCP), to test reject."""
    async def go():
        env = {"CAMPUS_CUSTOMS_ROLE": "agent", "CAMPUS_CUSTOMS_DB": str(SCRATCH_DB), "PATH": "/usr/bin:/bin",
               "FASTMCP_LOG_LEVEL": "WARNING"}
        async with Client(PythonStdioTransport(HW5 / "mcp_server" / "server.py", env=env, cwd=str(HW5),
                                               python_cmd=str(HW5 / ".venv" / "bin" / "python"))) as c:
            r = await c.call_tool("prepare_purchase_order", {"ticket_id": 103, "vendor_id": 1, "sku": "CC-HOOD-NAVY",
                                                             "size": "M", "qty": 12, "reason": "API reject test",
                                                             "prepared_by": "test"})
            return r.structured_content
    return asyncio.run(go())


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=30)

    h = c.get("/api/health").json()
    check("health: backend is on the SCRATCH database and audit file",
          h["database"].endswith("scratch/api_test.db") and h["audit_trail"].endswith("scratch/api_audit.json"), json.dumps(h))
    if not h["database"].endswith("scratch/api_test.db"):
        sys.exit("Refusing to continue: backend is not on scratch files.")

    # --- reset first, so the run starts from the original data
    r = c.post("/api/reset")
    check("reset: 200 and scratch db is byte-identical to the original", r.status_code == 200 and sha(SCRATCH_DB) == sha(ORIGINAL),
          r.text)

    # --- tickets + cash
    t = c.get("/api/tickets").json()
    check("tickets: three tickets, all open, with subject and requester",
          [(x["id"], x["status"]) for x in t] == [(101, "open"), (102, "open"), (103, "open")]
          and all(x["subject"] and x["requester"] for x in t), json.dumps([{k: x[k] for k in ("id", "requester", "subject", "status")} for x in t]))
    cash = c.get("/api/cash").json()
    check("cash: checking balance from cash_accounts", cash["balance"] == 3400.0, json.dumps(cash))

    # --- CORS / origin
    r = c.get("/api/tickets", headers={"Origin": BAD_ORIGIN})
    check("blocked: GET from another origin is refused (403)", r.status_code == 403, r.text)
    r = c.options("/api/tickets/101/run", headers={"Origin": BAD_ORIGIN, "Access-Control-Request-Method": "POST"})
    check("blocked: preflight from another origin is refused, no CORS header",
          r.status_code == 403 and "access-control-allow-origin" not in r.headers, f"status {r.status_code}")
    r = c.get("/api/tickets", headers={"Origin": GOOD_ORIGIN})
    check("allowed: GET from http://localhost:5173 gets the CORS header",
          r.status_code == 200 and r.headers.get("access-control-allow-origin") == GOOD_ORIGIN)
    r = c.options("/api/reset", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST"})
    check("allowed: preflight from http://127.0.0.1:5173 succeeds", r.status_code == 200, f"status {r.status_code}")

    # --- run route
    check("run: unknown ticket -> 404", c.post("/api/tickets/999/run").status_code == 404)
    t0 = time.time()
    r = c.post("/api/tickets/102/run")
    started_in = time.time() - t0
    run = r.json()
    check("run: ticket 102 starts in the background and returns right away (202)",
          r.status_code == 202 and started_in < 2, f"{started_in:.2f}s, {json.dumps(run)}")
    r2 = c.post("/api/tickets/101/run")
    check("run: a second run while one is going is refused (409)", r2.status_code == 409, r2.json().get("detail"))
    r3 = c.post("/api/reset")
    check("reset: refused during a run (409)", r3.status_code == 409, r3.json().get("detail"))

    growth, status = [], "running"
    deadline = time.time() + 420
    while status == "running" and time.time() < deadline:
        time.sleep(3)
        status = c.get(f"/api/runs/{run['run_id']}").json()["status"]
        ev = c.get("/api/events", params={"ticket": "102"}).json()
        growth.append(ev["total"])
        last = ev["events"][-1] if ev["events"] else {}
        print(f"   t+{time.time() - t0:5.0f}s run={status:8s} events={ev['total']:3d} latest: {last.get('agent')} "
              f"{last.get('step_type')} {last.get('tool_name') or ''}", flush=True)
    rs = c.get(f"/api/runs/{run['run_id']}").json()
    check("run: finished; status route reports it", rs["status"] == "finished", f"status={rs['status']} error={rs.get('error')}")
    check("events: appeared while the run was going (count grew between polls)",
          len(set(growth)) > 2 and growth == sorted(growth), f"event counts per poll: {growth}")
    ev = c.get("/api/events", params={"ticket": "102"}).json()["events"]
    times = [e["time"] for e in ev]
    check("events: newest last, filtered to ticket 102", times == sorted(times) and all(e["ticket"] == "102" for e in ev),
          f"{len(ev)} events")
    agents = sorted({e["agent"] for e in ev})
    tools = sorted({e["tool_name"] for e in ev if e["step_type"] == "tool_call"})
    models = sorted({e["model"] for e in ev if e.get("model")})
    print(f"   agents: {agents}\n   tools: {tools}\n   models: {models}")
    print(f"   decision: {json.dumps(rs['decision'])[:700]}")

    # --- pending items from the run
    items = c.get("/api/pending", params={"ticket": 102}).json()
    print("   pending for 102:", [(i["id"], i["item_type"], i["status"], i["amount"], i["prepared_by"]) for i in items])
    rent = next((i for i in items if i["item_type"] == "payment" and i["pay_kind"] == "rent" and i["status"] == "pending"), None)
    check("pending: run prepared a rent payment for 102", rent is not None)
    if rent is None:
        sys.exit("No rent payment to test approvals with.")
    tk = {x["id"]: x for x in c.get("/api/tickets").json()}
    check("ticket 102 stays open while its payment waits", tk[102]["status"] == "open" and tk[102]["waiting_on_human"] >= 1)

    # --- refused: not enough cash
    sql("UPDATE cash_accounts SET balance=100 WHERE name='checking'")
    r = c.post(f"/api/pending/{rent['id']}/approve", json={"by": "Test Manager"})
    still = sql("SELECT status FROM pending_items WHERE id=?", (rent["id"],))[0][0]
    check("approve: refused when cash is short (409), clear message, nothing changed",
          r.status_code == 409 and still == "pending" and sql("SELECT COUNT(*) FROM payments")[0][0] == 0
          and c.get("/api/cash").json()["balance"] == 100, r.json().get("detail"))
    sql("UPDATE cash_accounts SET balance=3400 WHERE name='checking'")

    # --- reject (a purchase order prepared through the agent role)
    po = prepare_po_via_agent_role()
    r = c.post(f"/api/pending/{po['item_id']}/reject", json={"by": "Test Manager"})
    check("reject: purchase order rejected", r.status_code == 200 and r.json()["status"] == "rejected", r.text)
    check("reject: ticket 103 stays open (it has never been run)", r.json()["ticket_resolved"] is False
          and c.get("/api/tickets").json()[2]["status"] == "open")
    for other in [i for i in items if i["id"] != rent["id"] and i["item_type"] in ("payment", "purchase_order") and i["status"] == "pending"]:
        c.post(f"/api/pending/{other['id']}/reject", json={"by": "Test Manager"})  # leave rent as the last one

    # --- approve that pays and resolves
    r = c.post(f"/api/pending/{rent['id']}/approve", json={"by": "Test Manager"})
    body = r.json()
    check("approve: rent paid through the human-only MCP tools", r.status_code == 200 and body["status"] == "paid",
          json.dumps(body.get("payment")))
    check("approve: payments row, cash down $2,400, lease next_due +1 month",
          sql("SELECT kind, ref_id, amount, approved_by FROM payments") == [("rent", 1, 2400.0, "Test Manager")]
          and c.get("/api/cash").json()["balance"] == 1000.0
          and sql("SELECT next_due FROM leases WHERE id=1")[0][0] == "2026-10-02")
    check("approve: last pending item -> ticket 102 resolved", body["ticket_resolved"] is True
          and sql("SELECT status FROM tickets WHERE id=102")[0][0] == "resolved")
    r = c.post("/api/tickets/102/run")
    check("run: resolved ticket refused (409)", r.status_code == 409, r.json().get("detail"))
    r = c.post(f"/api/pending/{rent['id']}/approve")
    check("approve: already-paid item refused (409)", r.status_code == 409, r.json().get("detail"))
    check("pending: list route with filters works", len(c.get("/api/pending", params={"status": "paid"}).json()) == 1)

    # --- reset
    before = len(json.loads(SCRATCH_AUDIT.read_text()))
    r = c.post("/api/reset")
    after_entries = json.loads(SCRATCH_AUDIT.read_text())
    check("reset: db restored byte-for-byte; original unchanged",
          r.status_code == 200 and sha(SCRATCH_DB) == sha(ORIGINAL) == "23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a",
          sha(ORIGINAL))
    check("reset: ticket statuses back to open, pending items and runs gone",
          [x["status"] for x in c.get("/api/tickets").json()] == ["open"] * 3 and c.get("/api/pending").json() == []
          and c.get("/api/runs").json()["runs"] == [])
    check("reset: audit trail kept every entry and added a reset marker",
          len(after_entries) == before + 1 and after_entries[-1]["step_type"] == "reset", f"{before} -> {len(after_entries)}")
    check("events: only events since the last reset are shown", c.get("/api/events").json()["total"] == 0)

    passed = sum(x["pass"] for x in results)
    print(f"\n{passed}/{len(results)} checks passed")
    (HW5 / "data" / "scratch" / "api_test_report.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
