"""Campus Customs MCP server.

Gives the shop's agents tools over the working database
data/campus_customs_new.db. The original data/campus_customs.db is never opened.

Two roles, picked by the CAMPUS_CUSTOMS_ROLE environment variable:
- "agent" (the default): read tools plus "prepare" tools that only add pending
  items for a human. The tools that approve or pay are not registered at all.
- "backend": everything above plus record_human_decision and
  execute_approved_payment, for the backend's approve route only.

CAMPUS_CUSTOMS_DB may point at a scratch copy inside data/scratch/ for tests.
Any other path, and the original database, is refused.
"""

import calendar
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

HW5_DIR = Path(__file__).resolve().parent.parent
WORKING_DB_PATH = HW5_DIR / "data" / "campus_customs_new.db"
ORIGINAL_DB_PATH = HW5_DIR / "data" / "campus_customs.db"
SCRATCH_DIR = HW5_DIR / "data" / "scratch"

ROLE = os.environ.get("CAMPUS_CUSTOMS_ROLE", "agent")
if ROLE not in ("agent", "backend"):
    raise RuntimeError(f"Unknown CAMPUS_CUSTOMS_ROLE {ROLE!r}; use 'agent' or 'backend'.")


def _resolve_db_path() -> Path:
    override = os.environ.get("CAMPUS_CUSTOMS_DB")
    if not override:
        return WORKING_DB_PATH
    path = Path(override).resolve()
    if path == ORIGINAL_DB_PATH.resolve():
        raise RuntimeError("Refusing to use the original database.")
    if path != WORKING_DB_PATH.resolve() and SCRATCH_DIR.resolve() not in path.parents:
        raise RuntimeError("CAMPUS_CUSTOMS_DB must be the working copy or a file inside data/scratch/.")
    return path


DB_PATH = _resolve_db_path()

# Hints to MCP clients about what a tool does.
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
PREPARE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
HUMAN_ONLY = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}

mcp = FastMCP("campus-customs")

# Small table added to the working copy only: everything an agent prepares waits here for a human.
PENDING_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    item_type TEXT NOT NULL CHECK (item_type IN ('payment', 'purchase_order', 'customer_message', 'price_override')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'paid', 'refused')),
    pay_kind TEXT CHECK (pay_kind IN ('invoice', 'rent')),
    ref_id INTEGER,
    vendor_id INTEGER,
    sku TEXT,
    size TEXT,
    qty INTEGER,
    unit_amount REAL,
    amount REAL,
    recipient TEXT,
    subject TEXT,
    body TEXT,
    reason TEXT,
    prepared_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    result_note TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
)
"""


def _check_db_file() -> None:
    if DB_PATH.resolve() == ORIGINAL_DB_PATH.resolve():
        raise RuntimeError("Refusing to open the original database.")
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")


def _connect_read_only() -> sqlite3.Connection:
    """Open the working copy in read-only mode. Refuses to touch the original."""
    _check_db_file()
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def _connect_write() -> sqlite3.Connection:
    """Open the working copy for a write. Callers wrap changes in BEGIN IMMEDIATE ... COMMIT."""
    _check_db_file()
    con = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(PENDING_ITEMS_SCHEMA)
    return con


def _has_pending_table(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'pending_items'").fetchone() is not None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cash_accounts(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT name, balance, date FROM cash_accounts ORDER BY name")]


def _open_invoices_for_vendor(con: sqlite3.Connection, vendor_id: int) -> list[dict]:
    return [
        dict(r)
        for r in con.execute(
            "SELECT id, amount, due_date FROM invoices WHERE vendor_id = ? AND status = 'open' ORDER BY id",
            (vendor_id,),
        )
    ]


def _add_one_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _ticket_exists(con: sqlite3.Connection, ticket_id: int) -> bool:
    return con.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


def _insert_pending(con: sqlite3.Connection, **fields) -> int:
    fields.setdefault("created_at", _now())
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = con.execute(f"INSERT INTO pending_items ({cols}) VALUES ({marks})", tuple(fields.values()))
    return cur.lastrowid


def _pending_row(con: sqlite3.Connection, item_id: int) -> dict | None:
    row = con.execute("SELECT * FROM pending_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def _today(con: sqlite3.Connection) -> date:
    """The shop's 'today' comes from desk.date_today, not the real clock."""
    row = con.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("desk table has no date_today row.")
    return date.fromisoformat(row["date_today"])


@mcp.tool(annotations=READ_ONLY)
def check_stock(sku: str, size: str, qty_needed: int = 1) -> dict:
    """Check how many of one item (sku + size) are on hand and whether that covers qty_needed.

    Example: check_stock("CC-TEE-WHITE", "S", 1) or check_stock("CC-HOOD-NAVY", "M", 20).
    """
    sku, size = sku.strip().upper(), size.strip().upper()
    with closing(_connect_read_only()) as con:
        row = con.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if row is None:
            known_sizes = [
                r["size"]
                for r in con.execute("SELECT size FROM inventory WHERE sku = ? ORDER BY size", (sku,))
            ]
            return {
                "found": False,
                "sku": sku,
                "size": size,
                "message": (
                    f"No inventory row for sku {sku} size {size}. "
                    + (f"Sizes on file for this sku: {known_sizes}." if known_sizes else "This sku is not in inventory.")
                ),
            }
    on_hand = row["qty"]
    return {
        "found": True,
        "sku": row["sku"],
        "name": row["name"],
        "size": row["size"],
        "location": row["location"],
        "qty_on_hand": on_hand,
        "qty_needed": qty_needed,
        "enough_in_stock": on_hand >= qty_needed,
        "shortfall": max(qty_needed - on_hand, 0),
    }


@mcp.tool(annotations=READ_ONLY)
def check_vendor_invoice(invoice_id: int) -> dict:
    """Look up an invoice and its vendor: amount, status, days overdue, lead time,
    and whether the vendor is blocked from shipping by any open (unpaid) invoice.

    Example: check_vendor_invoice(501).
    """
    with closing(_connect_read_only()) as con:
        today = _today(con)
        inv = con.execute(
            "SELECT id, vendor_id, amount, due_date, status, description FROM invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()
        if inv is None:
            return {"found": False, "invoice_id": invoice_id, "message": f"No invoice with id {invoice_id}."}
        vendor = con.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (inv["vendor_id"],)
        ).fetchone()
        open_invoices = _open_invoices_for_vendor(con, inv["vendor_id"])

    due = date.fromisoformat(inv["due_date"])
    is_open = inv["status"] == "open"
    result = {
        "found": True,
        "today": today.isoformat(),
        "invoice": {
            "id": inv["id"],
            "amount": inv["amount"],
            "due_date": inv["due_date"],
            "status": inv["status"],
            "description": inv["description"],
            "days_overdue": max((today - due).days, 0) if is_open else 0,
        },
        "vendor_open_invoices": open_invoices,
        "vendor_blocked": bool(open_invoices),
        "blocked_reason": (
            f"Vendor has {len(open_invoices)} open unpaid invoice(s); it won't ship new product until paid."
            if open_invoices
            else None
        ),
    }
    if vendor is None:
        result["vendor"] = None
        result["message"] = f"Invoice points to vendor_id {inv['vendor_id']}, which is not in the vendors table."
    else:
        result["vendor"] = dict(vendor)
    return result


@mcp.tool(annotations=READ_ONLY)
def check_rent_status(lease_id: int) -> dict:
    """Look up a lease's rent: amount, next due date, and days until due (negative = overdue).

    Example: check_rent_status(1).
    """
    with closing(_connect_read_only()) as con:
        today = _today(con)
        lease = con.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
    if lease is None:
        return {"found": False, "lease_id": lease_id, "message": f"No lease with id {lease_id}."}

    days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
    if days_until_due < 0:
        status = "overdue"
    elif days_until_due == 0:
        status = "due_today"
    elif days_until_due <= 7:
        status = "due_soon"
    else:
        status = "not_due_yet"
    return {
        "found": True,
        "today": today.isoformat(),
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "amount_due": lease["monthly_rent"],
        "next_due": lease["next_due"],
        "days_until_due": days_until_due,
        "status": status,
    }


@mcp.tool(annotations=READ_ONLY)
def list_tickets(status: str = "open") -> dict:
    """List tickets with a short line each. status: "open" (default), "closed", or "all".

    Example: list_tickets().
    """
    with closing(_connect_read_only()) as con:
        if status == "all":
            rows = con.execute("SELECT id, type, requester, subject, status FROM tickets ORDER BY id").fetchall()
        else:
            rows = con.execute(
                "SELECT id, type, requester, subject, status FROM tickets WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
    return {"status_filter": status, "count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool(annotations=READ_ONLY)
def get_ticket(ticket_id: int) -> dict:
    """Get one ticket's full record (type, requester, sku, size, qty, lease_id, invoice_id, notes)
    plus any pending items already prepared for it.

    Example: get_ticket(101).
    """
    with closing(_connect_read_only()) as con:
        today = _today(con)
        row = con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"found": False, "ticket_id": ticket_id, "message": f"No ticket with id {ticket_id}."}
        items = []
        if _has_pending_table(con):
            items = [
                dict(r)
                for r in con.execute(
                    "SELECT id, item_type, status, amount, prepared_by FROM pending_items WHERE ticket_id = ? ORDER BY id",
                    (ticket_id,),
                )
            ]
    return {"found": True, "today": today.isoformat(), "ticket": dict(row), "pending_items": items}


@mcp.tool(annotations=READ_ONLY)
def get_cash_balance() -> dict:
    """Show every cash account's balance and the total. Cash only goes out; there is no revenue.

    Example: get_cash_balance().
    """
    with closing(_connect_read_only()) as con:
        today = _today(con)
        accounts = _cash_accounts(con)
        pending_total = 0.0
        if _has_pending_table(con):
            pending_total = con.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM pending_items "
                "WHERE item_type = 'payment' AND status IN ('pending', 'approved')"
            ).fetchone()[0]
    if not accounts:
        return {"found": False, "message": "The cash_accounts table has no rows."}
    total = sum(a["balance"] for a in accounts)
    return {
        "found": True,
        "today": today.isoformat(),
        "accounts": accounts,
        "total_balance": total,
        "payments_awaiting_human": pending_total,
        "balance_if_all_awaiting_paid": total - pending_total,
    }


@mcp.tool(annotations=READ_ONLY)
def get_pricing_margin(sku: str, proposed_unit_price: float | None = None, qty: int = 1) -> dict:
    """Get unit cost and list price for a sku, and the margin at list price. If proposed_unit_price
    is given, also show the discount and margin at that price, and whether it is below cost.

    Example: get_pricing_margin("CC-HOOD-NAVY", 49.0, 20).
    """
    sku = sku.strip().upper()
    with closing(_connect_read_only()) as con:
        row = con.execute("SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
        name = con.execute("SELECT name FROM inventory WHERE sku = ? LIMIT 1", (sku,)).fetchone()
    if row is None:
        return {"found": False, "sku": sku, "message": f"No pricing row for sku {sku}."}
    cost, list_price = row["unit_cost"], row["list_price"]

    def margin(price: float) -> dict:
        return {
            "unit_price": price,
            "unit_margin": round(price - cost, 2),
            "margin_pct": round((price - cost) / price * 100, 1) if price else None,
            "total_revenue": round(price * qty, 2),
            "total_cost": round(cost * qty, 2),
            "total_margin": round((price - cost) * qty, 2),
        }

    result = {
        "found": True,
        "sku": sku,
        "name": name["name"] if name else None,
        "qty": qty,
        "unit_cost": cost,
        "list_price": list_price,
        "at_list_price": margin(list_price),
    }
    if proposed_unit_price is not None:
        result["at_proposed_price"] = margin(proposed_unit_price) | {
            "discount_pct": round((list_price - proposed_unit_price) / list_price * 100, 1),
            "below_cost": proposed_unit_price < cost,
        }
    return result


@mcp.tool(annotations=READ_ONLY)
def list_vendors(specialty_contains: str | None = None) -> dict:
    """List vendors with specialty, lead time, open invoices, and whether each is blocked from
    shipping (any open unpaid invoice blocks a vendor). Optional filter on specialty text.

    Example: list_vendors("apparel").
    """
    with closing(_connect_read_only()) as con:
        today = _today(con)
        if specialty_contains:
            rows = con.execute(
                "SELECT id, name, specialty, lead_days FROM vendors WHERE specialty LIKE ? ORDER BY id",
                (f"%{specialty_contains}%",),
            ).fetchall()
        else:
            rows = con.execute("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id").fetchall()
        vendors = []
        for v in rows:
            open_inv = _open_invoices_for_vendor(con, v["id"])
            vendors.append(
                dict(v)
                | {
                    "open_invoices": open_inv,
                    "blocked": bool(open_inv),
                    "earliest_arrival_if_unblocked": date.fromordinal(today.toordinal() + v["lead_days"]).isoformat(),
                }
            )
    if not vendors:
        return {"found": False, "message": f"No vendors match {specialty_contains!r}."}
    return {"found": True, "today": today.isoformat(), "vendors": vendors}


@mcp.tool(annotations=READ_ONLY)
def list_pending_items(ticket_id: int | None = None, status: str | None = None) -> dict:
    """List items waiting for (or decided by) a human: payments, purchase orders, price overrides,
    customer message drafts. Optional filters by ticket and status.

    Example: list_pending_items(ticket_id=101).
    """
    with closing(_connect_read_only()) as con:
        if not _has_pending_table(con):
            return {"count": 0, "items": [], "message": "Nothing has been prepared yet."}
        sql, params = "SELECT * FROM pending_items WHERE 1 = 1", []
        if ticket_id is not None:
            sql, params = sql + " AND ticket_id = ?", params + [ticket_id]
        if status is not None:
            sql, params = sql + " AND status = ?", params + [status]
        rows = [dict(r) for r in con.execute(sql + " ORDER BY id", params)]
    return {"count": len(rows), "items": rows}


@mcp.tool(annotations=PREPARE)
def prepare_payment(ticket_id: int, kind: Literal["invoice", "rent"], ref_id: int, reason: str, prepared_by: str = "agent") -> dict:
    """PREPARE (not make) a payment for a human to approve. kind="invoice" with ref_id = invoices.id,
    or kind="rent" with ref_id = leases.id. The amount always comes from the database.
    Nothing is paid and no cash moves until a human approves it.

    Example: prepare_payment(101, "invoice", 501, "Unblock Bulldog Print Co for the size S reprint").
    """
    with closing(_connect_write()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            if not _ticket_exists(con, ticket_id):
                con.execute("ROLLBACK")
                return {"prepared": False, "message": f"No ticket with id {ticket_id}."}
            if kind == "invoice":
                target = con.execute("SELECT id, amount, status, description FROM invoices WHERE id = ?", (ref_id,)).fetchone()
                if target is None:
                    con.execute("ROLLBACK")
                    return {"prepared": False, "message": f"No invoice with id {ref_id}."}
                if target["status"] != "open":
                    con.execute("ROLLBACK")
                    return {"prepared": False, "message": f"Invoice {ref_id} is '{target['status']}', not open; nothing to pay."}
                amount, what = target["amount"], f"invoice {ref_id}: {target['description']}"
            else:
                target = con.execute("SELECT id, monthly_rent, space_name, next_due FROM leases WHERE id = ?", (ref_id,)).fetchone()
                if target is None:
                    con.execute("ROLLBACK")
                    return {"prepared": False, "message": f"No lease with id {ref_id}."}
                amount, what = target["monthly_rent"], f"rent for {target['space_name']} due {target['next_due']}"
            duplicate = con.execute(
                "SELECT id FROM pending_items WHERE item_type = 'payment' AND pay_kind = ? AND ref_id = ? "
                "AND status IN ('pending', 'approved')",
                (kind, ref_id),
            ).fetchone()
            if duplicate:
                con.execute("ROLLBACK")
                return {"prepared": False, "existing_item_id": duplicate["id"],
                        "message": f"A {kind} payment for ref_id {ref_id} is already waiting for a human (item {duplicate['id']})."}
            item_id = _insert_pending(
                con, ticket_id=ticket_id, item_type="payment", pay_kind=kind, ref_id=ref_id,
                amount=amount, reason=reason, prepared_by=prepared_by,
            )
            cash = sum(a["balance"] for a in _cash_accounts(con))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return {
        "prepared": True, "item_id": item_id, "status": "pending", "kind": kind, "ref_id": ref_id,
        "amount": amount, "for": what, "cash_balance_now": cash, "cash_covers_it": cash >= amount,
        "note": "Waiting for human approval. Nothing has been paid.",
    }


@mcp.tool(annotations=PREPARE)
def prepare_purchase_order(ticket_id: int, vendor_id: int, sku: str, size: str, qty: int, reason: str, prepared_by: str = "agent") -> dict:
    """PREPARE a purchase order draft for a human to approve. Unit cost comes from the pricing table.
    Flags whether the vendor is blocked by an open invoice and when stock could arrive.
    Nothing is sent to the vendor.

    Example: prepare_purchase_order(103, 1, "CC-HOOD-NAVY", "M", 12, "Cover the 12-hoodie shortfall").
    """
    sku, size = sku.strip().upper(), size.strip().upper()
    if qty <= 0:
        return {"prepared": False, "message": "qty must be at least 1."}
    with closing(_connect_write()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            today = _today(con)
            if not _ticket_exists(con, ticket_id):
                con.execute("ROLLBACK")
                return {"prepared": False, "message": f"No ticket with id {ticket_id}."}
            vendor = con.execute("SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
            price = con.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
            stock = con.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
            problems = [
                msg for ok, msg in [
                    (vendor, f"No vendor with id {vendor_id}."),
                    (price, f"No pricing row for sku {sku}."),
                    (stock, f"No inventory row for sku {sku} size {size}."),
                ] if ok is None
            ]
            if problems:
                con.execute("ROLLBACK")
                return {"prepared": False, "message": " ".join(problems)}
            open_inv = _open_invoices_for_vendor(con, vendor_id)
            amount = round(price["unit_cost"] * qty, 2)
            item_id = _insert_pending(
                con, ticket_id=ticket_id, item_type="purchase_order", vendor_id=vendor_id, sku=sku, size=size,
                qty=qty, unit_amount=price["unit_cost"], amount=amount, reason=reason, prepared_by=prepared_by,
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return {
        "prepared": True, "item_id": item_id, "status": "pending", "vendor": vendor["name"], "sku": sku,
        "size": size, "qty": qty, "unit_cost": price["unit_cost"], "estimated_cost": amount,
        "vendor_blocked": bool(open_inv), "blocking_invoices": open_inv,
        "earliest_arrival_if_sent_today": date.fromordinal(today.toordinal() + vendor["lead_days"]).isoformat(),
        "note": "Draft only. Not sent to the vendor; a human must approve"
                + (" and the vendor's open invoice must be paid first." if open_inv else "."),
    }


@mcp.tool(annotations=PREPARE)
def prepare_price_override(ticket_id: int, sku: str, qty: int, unit_price: float, reason: str, prepared_by: str = "agent") -> dict:
    """PREPARE a price override (discount) for a human to approve. Refuses any price below unit cost.

    Example: prepare_price_override(103, "CC-HOOD-NAVY", 20, 49.0, "Bulk discount for Yale AI Club").
    """
    sku = sku.strip().upper()
    if qty <= 0 or unit_price <= 0:
        return {"prepared": False, "message": "qty and unit_price must be positive."}
    with closing(_connect_write()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            if not _ticket_exists(con, ticket_id):
                con.execute("ROLLBACK")
                return {"prepared": False, "message": f"No ticket with id {ticket_id}."}
            row = con.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
            if row is None:
                con.execute("ROLLBACK")
                return {"prepared": False, "message": f"No pricing row for sku {sku}."}
            if unit_price < row["unit_cost"]:
                con.execute("ROLLBACK")
                return {"prepared": False, "message": f"Refused: ${unit_price} is below the unit cost of ${row['unit_cost']}."}
            item_id = _insert_pending(
                con, ticket_id=ticket_id, item_type="price_override", sku=sku, qty=qty, unit_amount=unit_price,
                amount=round(unit_price * qty, 2), reason=reason, prepared_by=prepared_by,
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return {
        "prepared": True, "item_id": item_id, "status": "pending", "sku": sku, "qty": qty,
        "unit_price": unit_price, "list_price": row["list_price"], "unit_cost": row["unit_cost"],
        "discount_pct": round((row["list_price"] - unit_price) / row["list_price"] * 100, 1),
        "margin_pct": round((unit_price - row["unit_cost"]) / unit_price * 100, 1),
        "total": round(unit_price * qty, 2),
        "note": "Waiting for human approval. The customer has not been told.",
    }


@mcp.tool(annotations=PREPARE)
def prepare_customer_message(ticket_id: int, recipient: str, subject: str, body: str, prepared_by: str = "agent") -> dict:
    """Save a DRAFT message to a customer on the board. It is never emailed or sent; a human reviews it.

    Example: prepare_customer_message(101, "Tauhid Zaman", "Your size S tee", "Hi Tauhid, ...").
    """
    if not body.strip():
        return {"prepared": False, "message": "The draft body is empty."}
    with closing(_connect_write()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            if not _ticket_exists(con, ticket_id):
                con.execute("ROLLBACK")
                return {"prepared": False, "message": f"No ticket with id {ticket_id}."}
            item_id = _insert_pending(
                con, ticket_id=ticket_id, item_type="customer_message", recipient=recipient,
                subject=subject, body=body, prepared_by=prepared_by,
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return {"prepared": True, "item_id": item_id, "status": "pending",
            "note": "Draft saved on the board. Nothing was sent."}


# ---------------------------------------------------------------------------
# Human-only tools. Registered only when CAMPUS_CUSTOMS_ROLE=backend, so the
# agents' server process does not have them at all.
# ---------------------------------------------------------------------------


def record_human_decision(item_id: int, decision: Literal["approve", "reject"], decided_by: str) -> dict:
    """Record a human's approve/reject decision on a pending item. Backend approve route only.

    Example: record_human_decision(1, "approve", "Store manager").
    """
    if not decided_by.strip():
        return {"ok": False, "message": "decided_by must name the human who decided."}
    with closing(_connect_write()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            item = _pending_row(con, item_id)
            if item is None:
                con.execute("ROLLBACK")
                return {"ok": False, "message": f"No pending item {item_id}."}
            # A payment approved but refused for lack of cash stays 'approved' and unpaid; a human may still reject it.
            unpaid_approved = item["status"] == "approved" and item["item_type"] == "payment" and decision == "reject"
            if item["status"] != "pending" and not unpaid_approved:
                con.execute("ROLLBACK")
                return {"ok": False, "message": f"Item {item_id} is already '{item['status']}'."}
            new_status = "approved" if decision == "approve" else "rejected"
            con.execute(
                "UPDATE pending_items SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                (new_status, decided_by.strip(), _now(), item_id),
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return {"ok": True, "item_id": item_id, "status": new_status, "decided_by": decided_by.strip()}


def execute_approved_payment(item_id: int, account: str = "checking") -> dict:
    """Pay a human-approved payment item. Backend approve route only.

    Refuses unless the item is a payment with status 'approved' and a named approver, the invoice is
    still open, and the account holds enough cash (no negative balance). In one transaction it:
    inserts a payments row, lowers the cash balance, and marks the invoice paid or moves the lease's
    next_due forward one month; then marks the item 'paid'.
    """
    with closing(_connect_write()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            today = _today(con)
            item = _pending_row(con, item_id)

            def refuse(msg: str, mark_refused: bool = False) -> dict:
                if mark_refused:
                    con.execute(
                        "UPDATE pending_items SET status = 'refused', result_note = ? WHERE id = ?", (msg, item_id)
                    )
                    con.execute("COMMIT")
                else:
                    con.execute("ROLLBACK")
                return {"paid": False, "item_id": item_id, "message": msg}

            if item is None:
                return refuse(f"No pending item {item_id}.")
            if item["item_type"] != "payment":
                return refuse(f"Item {item_id} is a {item['item_type']}, not a payment.")
            if item["status"] != "approved" or not item["decided_by"]:
                return refuse(f"Item {item_id} is '{item['status']}'. Only a human-approved payment can be paid.")

            acct = con.execute("SELECT name, balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
            if acct is None:
                return refuse(f"No cash account named {account!r}.")

            amount = item["amount"]
            if item["pay_kind"] == "invoice":
                inv = con.execute("SELECT amount, status FROM invoices WHERE id = ?", (item["ref_id"],)).fetchone()
                if inv is None:
                    return refuse(f"Invoice {item['ref_id']} no longer exists.", mark_refused=True)
                if inv["status"] != "open":
                    return refuse(f"Invoice {item['ref_id']} is already '{inv['status']}'.", mark_refused=True)
                amount = inv["amount"]
            else:
                lease = con.execute("SELECT monthly_rent, next_due FROM leases WHERE id = ?", (item["ref_id"],)).fetchone()
                if lease is None:
                    return refuse(f"Lease {item['ref_id']} no longer exists.", mark_refused=True)
                amount = lease["monthly_rent"]

            if acct["balance"] < amount:
                return refuse(
                    f"Not enough cash: {account} holds ${acct['balance']:.2f}, payment needs ${amount:.2f}. "
                    "Refused so the balance never goes negative."
                )

            cur = con.execute(
                "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
                (item["pay_kind"], item["ref_id"], amount, account, today.isoformat(), item["decided_by"]),
            )
            payment_id = cur.lastrowid
            con.execute(
                "UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
                (amount, today.isoformat(), account),
            )
            if item["pay_kind"] == "invoice":
                con.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (item["ref_id"],))
                effect = f"invoice {item['ref_id']} marked paid"
            else:
                new_due = _add_one_month(date.fromisoformat(lease["next_due"])).isoformat()
                con.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, item["ref_id"]))
                effect = f"lease {item['ref_id']} next_due moved to {new_due}"
            con.execute(
                "UPDATE pending_items SET status = 'paid', result_note = ? WHERE id = ?",
                (f"payment {payment_id}; {effect}", item_id),
            )
            new_balance = con.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()[0]
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
    return {"paid": True, "item_id": item_id, "payment_id": payment_id, "kind": item["pay_kind"],
            "ref_id": item["ref_id"], "amount": amount, "account": account, "new_balance": new_balance,
            "effect": effect, "approved_by": item["decided_by"]}


if ROLE == "backend":
    mcp.tool(annotations=HUMAN_ONLY, tags={"human_only"})(record_human_decision)
    mcp.tool(annotations=HUMAN_ONLY, tags={"human_only"})(execute_approved_payment)


if __name__ == "__main__":
    mcp.run(show_banner=False)
