# Campus Customs MCP server

This is an MCP server built with FastMCP. It's the agents' **only** source of shop facts and their only way to record work, so their answers come from the database and not from guesses.

## Database

- Uses **only** `data/campus_customs_new.db`, the working copy. For tests, `CAMPUS_CUSTOMS_DB` may point at a scratch copy inside `data/scratch/`. Any other path is refused.
- Never opens the original `data/campus_customs.db`. The code refuses it explicitly.
- Read tools open the file read-only (`mode=ro` plus `PRAGMA query_only`). Write tools use one `BEGIN IMMEDIATE` transaction each. Every query uses parameters.
- "Today" means `desk.date_today` (2026-08-31), not the real clock.
- Adds one table to the working copy, `pending_items`, holding prepared payments, purchase orders, price overrides and customer message drafts. It's created on the first prepare.

## Roles

`CAMPUS_CUSTOMS_ROLE` decides which tools exist in the process:

| Role | Who starts it | Tools |
|---|---|---|
| `agent` (default) | the agent team (`backend/team.py`) and Claude Code via `.mcp.json` | read and prepare tools |
| `backend` | only the backend's approve route (later problem) | read and prepare tools, plus the two human-only tools |

In the `agent` role the human-only tools are not registered, so an agent can't list or call them.

## Read tools

| Tool | Inputs | Reads | Returns |
|---|---|---|---|
| `check_stock` | `sku`, `size`, `qty_needed` (default 1) | `inventory` | qty on hand, location, `enough_in_stock`, `shortfall` |
| `check_vendor_invoice` | `invoice_id` | `invoices`, `vendors`, `desk` | invoice amount, due date, status, `days_overdue`; vendor name and `lead_days`; `vendor_blocked` if the vendor has any open invoice |
| `check_rent_status` | `lease_id` | `leases`, `desk` | `amount_due`, `next_due`, `days_until_due` (negative means overdue), and a status (`overdue`, `due_today`, `due_soon`, `not_due_yet`) |
| `list_tickets` | `status` (default `open`; or `closed`, `all`) | `tickets` | id, type, requester, subject, status |
| `get_ticket` | `ticket_id` | `tickets`, `pending_items` | the full ticket and any items already prepared for it |
| `get_cash_balance` | none | `cash_accounts`, `pending_items` | balance per account, total, payments awaiting a human, and the balance if they're all paid |
| `get_pricing_margin` | `sku`, `proposed_unit_price` (optional), `qty` | `pricing`, `inventory` | unit cost, list price, margin at list, plus discount %, margin and `below_cost` at the proposed price |
| `list_vendors` | `specialty_contains` (optional) | `vendors`, `invoices`, `desk` | each vendor's lead days, open invoices, `blocked`, and earliest arrival if unblocked |
| `list_pending_items` | `ticket_id`, `status` (both optional) | `pending_items` | prepared items and their status |

## Prepare tools (only add a `pending` row; nothing is paid, sent or ordered)

| Tool | Inputs | Reads | Writes |
|---|---|---|---|
| `prepare_payment` | `ticket_id`, `kind` (`invoice` or `rent`), `ref_id`, `reason` | `tickets`, `invoices` or `leases`, `cash_accounts` | `pending_items` (amount taken from the database; refuses invoices that aren't open and duplicates) |
| `prepare_purchase_order` | `ticket_id`, `vendor_id`, `sku`, `size`, `qty`, `reason` | `tickets`, `vendors`, `pricing`, `inventory`, `invoices` | `pending_items` (cost from pricing; flags a blocked vendor) |
| `prepare_price_override` | `ticket_id`, `sku`, `qty`, `unit_price`, `reason` | `tickets`, `pricing` | `pending_items` (refuses prices below unit cost) |
| `prepare_customer_message` | `ticket_id`, `recipient`, `subject`, `body` | `tickets` | `pending_items` (a draft only; never sent) |

## Human-only tools (backend role only)

| Tool | Inputs | Effect |
|---|---|---|
| `record_human_decision` | `item_id`, `decision` (`approve`/`reject`), `decided_by` | moves a pending item to `approved` or `rejected` and records who decided |
| `execute_approved_payment` | `item_id`, `account` (default `checking`) | pays an approved payment in one transaction: refuses if not approved or not enough cash; otherwise inserts a `payments` row, lowers `cash_accounts.balance`, and marks the invoice `paid` or moves the lease's `next_due` forward one month |

If a record isn't found, a tool returns `"found": false` (or `"prepared": false` / `"paid": false`) and a message saying what's wrong. It never makes up values.

## Running

```
.venv/bin/python mcp_server/server.py
```

This runs over stdio in the `agent` role.
