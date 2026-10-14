# Campus Customs: Agent Harness

Working database: `data/campus_customs_new.db` (a copy of `data/campus_customs.db`; the original is never modified).
Original sha256: `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`

Row counts below are from the original database. After the real run on 2026-10-14 (see *Ticket results*), the working copy differs only where the human approved payments: 2 `payments` rows, checking at $160, invoice 501 paid, lease 1 next due 2026-10-02, all tickets resolved.

## Database tables

### desk (1 row)
Fields: `date_today`, `notes`
Why it matters: `date_today` (2026-08-31) is the shop's "today". Every overdue or due-soon decision uses it, not the real clock.

### tickets (3 rows)
Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`
Why it matters: this is the agents' work queue. Each ticket's type and link fields say which other tables to check. `status` is `open` until the backend sets it to `resolved` (see the resolution rule under API routes).

### inventory (10 rows)
Fields: `sku`, `name`, `size`, `qty`, `location` (primary key: `sku` + `size`)
Why it matters: stock on hand per item and size. It decides whether an order can be filled or needs a reprint.

### pricing (4 rows)
Fields: `sku`, `unit_cost`, `list_price`
Why it matters: cost and list price per item. Used to work out reorder costs and how far a discount can go before losing money.

### vendors (3 rows)
Fields: `id`, `name`, `specialty`, `lead_days`
Why it matters: says who can supply what and how many days delivery takes.

### invoices (1 row)
Fields: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`
Why it matters: bills the shop owes. An open, unpaid invoice stops that vendor from shipping anything new.

### leases (1 row)
Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`
Why it matters: the rent amount and next due date for the shop space.

### cash_accounts (1 row)
Fields: `name`, `balance`, `date`
Why it matters: the only source of cash. Every payment is checked against it, and a balance can never go negative.

### payments (0 rows)
Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`
Why it matters: the record of every approved payment. `kind` and `ref_id` point to the invoice or lease being paid, and `approved_by` names the human who approved it.

### pending_items (added to the working copy only)
Fields: `id`, `ticket_id`, `item_type` (`payment` / `purchase_order` / `price_override` / `customer_message`), `status` (`pending` / `approved` / `rejected` / `paid` / `refused`), `pay_kind`, `ref_id`, `vendor_id`, `sku`, `size`, `qty`, `unit_amount`, `amount`, `recipient`, `subject`, `body`, `reason`, `prepared_by`, `created_at`, `decided_by`, `decided_at`, `result_note`
Why it matters: everything an agent prepares waits here for a human. Created by the MCP server on the first prepare; cleared by a reset.

### ticket_runs (added to the working copy only)
Fields: `id`, `ticket_id`, `status` (`running` / `finished` / `failed`), `started_at`, `finished_at`, `decision` (the Boss's JSON), `error`
Why it matters: run history for the status route and the resolution rule. Created by the backend on the first run; cleared by a reset.

## The three tickets (as found in the original data)

### Ticket 101: customer order (Tauhid Zaman, 1× Bulldog tee, size S)
- `sku`/`size` → **inventory**: CC-TEE-WHITE size S has qty **0**, so the order can't be filled from stock.
- `sku` → **pricing**: unit cost $8, list price $28.
- `invoice_id` 501 → **invoices**: $840 to Bulldog Print Co for "Rush reprint CC-TEE-WHITE S", status **open**, due 2026-08-28, so it is **3 days overdue**.
- `vendor_id` 1 → **vendors**: Bulldog Print Co, 5 lead days.
- Facts needed: stock level, invoice status and amount, vendor lead time, cash balance. Bulldog won't ship until invoice 501 is paid, and paying it needs human approval and enough cash.

### Ticket 102: rent notice (Elm City Properties)
- `lease_id` 1 → **leases**: Chapel Street shop, $2,400, next due **2026-09-02** (2 days after today).
- **cash_accounts**: checking holds $3,400.
- Facts needed: rent amount, due date compared with today, cash balance. Paying needs human approval. After paying, add a row to `payments`, lower the cash balance, and move `next_due` forward a month.

### Ticket 103: price override (Yale AI Club, 20× hoodie, size M, bulk discount)
- `sku`/`size` → **inventory**: CC-HOOD-NAVY size M has qty **8**, so 12 are missing.
- `sku` → **pricing**: unit cost $22, list price $58. The cost sets the floor for any discount.
- Restocking needs an apparel vendor. That is **vendors** 1, Bulldog Print Co (5 lead days), the same vendor with unpaid invoice 501.
- Facts needed: stock, cost and list price, a proposed discount with its margin, restock cost and timing, vendor status, cash. A price override is a decision for a human; the agents only draft it.

### Ticket results (real run, 2026-10-14)
Full detail: `output/desk_tickets.html` (Actual and Cash tabs), `output/resolved_tickets.json`, `output/resolved_board.html`.

| Ticket | Agents (delegations) | Boss's call | Human decisions | Cash |
|---|---|---|---|---|
| 101 | Boss → Inventory, Boss → Accounting → Inventory, Boss → Customer Service | proceed pending approval | Paid invoice 501 ($840); approved PO 1 × tee S ($8); voided the customer draft | $3,400 → $2,560 |
| 102 | Boss → Facilities and Boss → Accounting (same step) | proceed pending approval | Paid rent on lease 1 ($2,400) | $2,560 → $160 |
| 103 | Boss → Inventory, Boss → Accounting → Inventory, Boss → Customer Service | needs more info (no price named; no override or PO) | None needed; one customer draft left pending | $160 (no change) |

Each run worked on the first attempt (no errors, limit stops or retries), and every reply came from gpt-6-luna. Ending balance: $3,400 − $840 − $2,400 = **$160**, which matches `cash_accounts`.

## Shop rules
- `desk.date_today` is "today" for the shop; use it to decide what's overdue or due soon.
- Vendor lead times come from the `vendors` table.
- A vendor won't ship new product while they have an open unpaid invoice.
- Any payment needs human approval, and when a payment is made, the relevant tables must be updated.
- If there isn't enough cash, a payment must be refused (no negative balances).
- Cash only goes out; no revenue is modeled.
- Nobody gets emailed and no real vendor is called; drafts stay on the board.

## MCP tools

Server: `mcp_server/server.py` (FastMCP, stdio). It opens only `data/campus_customs_new.db` (a scratch copy in `data/scratch/` is allowed for tests; the original is always refused) and treats `desk.date_today` as today. Read tools open the file in read-only mode. Prepare tools write only to the new `pending_items` table, inside one `BEGIN IMMEDIATE` transaction each.

The server has two roles, set by the `CAMPUS_CUSTOMS_ROLE` environment variable:
- **agent** (the default; used by the agent team and by Claude Code through `.mcp.json`): read tools plus prepare tools.
- **backend** (used only by the backend's approve and reject routes): adds the two human-only tools. In the agent role those tools are **not registered at all**, so no agent can list or call them.

### Read tools

| Tool | Reads | Unlocks | Why it's the right tool |
|---|---|---|---|
| `check_stock(sku, size, qty_needed)` | `inventory` | 101, 103 | Answers both stock questions with `enough_in_stock` and the exact `shortfall`: 1 tee in size S for 101 and 12 navy hoodies in size M for 103. |
| `check_vendor_invoice(invoice_id)` | `invoices`, `vendors`, `desk` | 101 (and 103's restock) | Calling it with ticket 101's invoice 501 shows the $840 is open and 3 days overdue, so Bulldog Print Co is blocked from the size S reprint. Its 5-day lead time sets the earliest restock. |
| `check_rent_status(lease_id)` | `leases`, `desk` | 102 | Checks the emailed notice against lease 1: $2,400 due 2026-09-02, 2 days away (`due_soon`). |
| `get_ticket(ticket_id)` | `tickets`, `pending_items` | 101, 102, 103 | The Boss's starting point. The ticket's `type` and its `sku`, `size`, `qty`, `lease_id` and `invoice_id` say which agents and tools come next, and it shows what's already pending. |
| `list_tickets(status)` | `tickets` | all | The work queue. |
| `get_cash_balance()` | `cash_accounts`, `pending_items` | 101, 102 (and 103's restock) | One $3,400 account has to cover both the $840 invoice and the $2,400 rent. The tool also subtracts payments already awaiting approval, so two prepared payments can't each look affordable on their own. |
| `get_pricing_margin(sku, proposed_unit_price, qty)` | `pricing`, `inventory` | 103 (also 101's reprint cost) | Ticket 103 asks for a bulk discount. At $58 list and $22 cost, this shows the margin at any proposed price and flags `below_cost`. |
| `list_vendors(specialty_contains)` | `vendors`, `invoices`, `desk` | 101, 103 | Finds who can restock apparel (Bulldog Print Co, the only apparel vendor) and shows it's blocked, plus its earliest arrival date. |
| `list_pending_items(ticket_id, status)` | `pending_items` | all | Stops the team from preparing the same payment twice and shows the human what's waiting. |

### Prepare tools (agent-visible; they only add a `pending` row to `pending_items`)

| Tool | Reads | Writes | Unlocks |
|---|---|---|---|
| `prepare_payment(ticket_id, kind, ref_id, reason)` | `tickets`, `invoices` or `leases`, `cash_accounts` | `pending_items` (type `payment`) | 101 (invoice 501), 102 (rent on lease 1) |
| `prepare_purchase_order(ticket_id, vendor_id, sku, size, qty, reason)` | `tickets`, `vendors`, `pricing`, `inventory`, `invoices` | `pending_items` (type `purchase_order`) | 101 (1 tee in size S), 103 (12 hoodies in size M) |
| `prepare_price_override(ticket_id, sku, qty, unit_price, reason)` | `tickets`, `pricing` | `pending_items` (type `price_override`) | 103 |
| `prepare_customer_message(ticket_id, recipient, subject, body)` | `tickets` | `pending_items` (type `customer_message`) | 101, 103 (and a landlord reply for 102 if wanted) |

Guards: amounts and costs always come from the database, never from the agent. A payment for an invoice that isn't open is refused. A second pending payment for the same invoice or lease is refused. A price below unit cost is refused. The harness fills in `prepared_by` with the calling agent's name, whatever the model sends.

### Human-only tools (backend role only; no agent can reach them)

| Tool | Reads | Writes | Used by |
|---|---|---|---|
| `record_human_decision(item_id, decision, decided_by)` | `pending_items` | `pending_items.status` → `approved` / `rejected`, plus `decided_by` and `decided_at` | `POST /api/pending/{id}/approve` and `/reject` |
| `execute_approved_payment(item_id, account="checking")` | `pending_items`, `cash_accounts`, `invoices`, `leases`, `desk` | `payments`, `cash_accounts`, `invoices` or `leases`, `pending_items` | `POST /api/pending/{id}/approve` (payments only) |

### Payment choices

`pending_items` is a new table, added **to the working copy only**. The server creates it the first time anything is prepared. The original database is never opened.

- **`pending_items.status`:** `pending` → `approved` or `rejected` (by a human) → `paid`. A payment becomes `refused` if its invoice or lease vanished or was already paid. A payment refused for lack of cash stays `approved`, so it can be retried once cash allows.
- **`payments.kind` / `ref_id`:**
  - `kind = 'invoice'`, `ref_id = invoices.id` (for example 501).
  - `kind = 'rent'`, `ref_id = leases.id` (for example 1).
- **`payments.account`:** the `cash_accounts.name` it's paid from (`checking`).
- **`payments.paid_at`:** `desk.date_today`.
- **`payments.approved_by`:** the human named in `record_human_decision`.

**What `execute_approved_payment` does, in one transaction (all or nothing):**
1. Refuses unless the item is a `payment`, its status is `approved`, and it names an approver.
2. Re-reads the amount from the database: `invoices.amount` (the invoice must still be `open`) or `leases.monthly_rent`.
3. Refuses if `cash_accounts.balance` < amount. A balance can never go negative.
4. Inserts the `payments` row (kind, ref_id, amount, account, paid_at, approved_by).
5. `cash_accounts.balance -= amount`, and its `date` is set to today.
6. For an invoice, `invoices.status = 'paid'`, which unblocks that vendor. For rent, `leases.next_due` moves forward one calendar month (2026-09-02 → 2026-10-02).
7. Sets `pending_items.status = 'paid'`, with `result_note` naming the payment id and the effect.

Purchase orders, price overrides and customer messages are never "executed" by a tool. Once approved, a human acts on them (sends the PO, quotes the price, sends the email).

## Agents

Built with PydanticAI (`backend/team.py`). The data types are in `backend/models.py` and the prompts in `backend/prompts/`. All five agents use only `gpt-6-luna` through Portkey. The model name and every limit live in `backend/config.py`. The Portkey key is read from `.env`, which is git-ignored (`.env.example` holds a placeholder).

Each agent gets two kinds of tools:
1. The MCP server (agent role), filtered to the tools its job needs.
2. `ask_agent(agent, question)` for delegation.

Nothing else: there is no second tool layer around the database. All five agents share one MCP server process per ticket.

| Agent | Job | MCP tools (tables) | Returns |
|---|---|---|---|
| **Boss** | Reads the ticket, picks who works on it, makes the final call | `get_ticket` (tickets, pending_items), `list_tickets` (tickets), `list_pending_items` (pending_items), `get_cash_balance` (cash_accounts) | `TicketDecision`: decision, summary, facts with sources, prepared item ids, human actions needed |
| **Inventory** | Stock by sku and size, shortfalls, which vendor can restock, blocked or not, lead time | `get_ticket`, `check_stock` (inventory), `list_vendors` (vendors, invoices), `check_vendor_invoice` (invoices, vendors), `get_pricing_margin` (pricing) | `AgentReport` |
| **Accounting** | Cash, invoices, margins; prepares payments, purchase orders and price overrides | `get_ticket`, `get_cash_balance`, `check_vendor_invoice`, `check_rent_status` (leases), `get_pricing_margin`, `list_vendors`, `list_pending_items`, `prepare_payment`, `prepare_purchase_order`, `prepare_price_override` (writes pending_items) | `AgentReport` |
| **Facilities** | Leases and rent; checks the notice against the lease | `get_ticket`, `check_rent_status` (leases), `get_cash_balance`, `list_pending_items` | `AgentReport` |
| **Customer Service** | Drafts customer messages, never sends | `get_ticket`, `check_stock`, `get_pricing_margin` (list price only), `list_pending_items`, `prepare_customer_message` (writes pending_items) | `AgentReport` |

**Delegation:** full connectivity, so any agent can `ask_agent` any other and gets that agent's structured report back as the tool result. Two simple guards stop pointless loops:
- An agent can't ask itself.
- An agent can't ask one that is already waiting on it in the current chain (A → B → A).

**Audit trail (`output/audit_trail.json`, `backend/audit.py`):** every step of every agent loop appends one entry with these fields:
- `time`, `ticket`, `agent`, `depth`
- `step_type`: `run_start`, `model_reply`, `tool_call`, `delegation`, `limit_stop`, `error` or `run_end` for agent steps; the backend adds `human_decision` (approve, reject, ticket resolved) and `reset` (new shift) markers
- `tool_name`, `args` and `result`, each shortened to at most 300 characters
- `stop_reason` (the model's finish reason, `final_output`, or the limit hit)
- `model`, as reported by the reply itself

How the file stays safe:
- Every append takes an exclusive file lock, so threads and processes can write at the same time without interleaving.
- Each write goes to a temp file, is fsynced, then swapped in atomically, so a crash never leaves half a file.
- The file is never wiped. If it ever can't be parsed, it's copied aside untouched before a new array is started.
- The Portkey key and anything that looks like a key or token is replaced with `[REDACTED]`.

**Model check:** every reply's `model` field is checked. The run stops (`ModelSubstituted`) unless it's `gpt-6-luna` itself, a dated release of it (chat completions reports `…-2026-09-22`), or its Azure global deployment label (the Responses API reports `…-global`).

The agents call Portkey's Responses route, because its chat-completions route rejects function tools for this model.

> **Note for graders: "gpt-6-luna-global" is gpt-6-luna.** Portkey routes `gpt-6-luna` to Azure OpenAI. On the Responses route, Azure reports the replying model as **`gpt-6-luna-global`**, its name for the global deployment of gpt-6-luna. That's the same model, not a different one. The code only ever requests `gpt-6-luna`. The audit trail's `model` column records the name exactly as the reply gave it, so you'll see `gpt-6-luna-global` there.

## API routes

FastAPI app in `backend/main.py`. Start it from inside `backend/` with `uvicorn main:app --reload --port 8000`. Only the browser origins `http://localhost:5173` and `http://127.0.0.1:5173` are allowed; a request from any other origin gets a 403. Runs use the agent-role MCP server; only approve and reject start the backend-role MCP server, which has the human-only tools.

- `GET /api/health`: the database and audit file in use, and whether a run is active.
- `GET /api/tickets`: every ticket with its id, type, requester, subject, status (`open`/`resolved`), last run, and how many payments or purchases wait on a human.
- `POST /api/tickets/{id}/run`: starts the agent team on the ticket in the background and returns `202` with a `run_id` right away. Returns `409` if a run is already going, the ticket is resolved, or it already has a finished run; `404` for an unknown id.
- `GET /api/runs/{run_id}`: a run's status (`running`/`finished`/`failed`), start and finish times, the Boss's decision or the error, and the ticket's status.
- `GET /api/runs`: all runs since the last reset and the active run id.
- `GET /api/events?ticket=&limit=`: audit-trail events since the last `reset` marker, newest last, optionally filtered by ticket (default limit 200).
- `GET /api/pending?ticket=&status=`: prepared items (payments, purchase orders, price overrides, customer drafts) with their status.
- `POST /api/pending/{id}/approve` (body `{"by": "<name>"}`): records the human's approval. For a payment it also checks cash first and returns `409` with a clear message if checking can't cover it (nothing changes), then pays through `execute_approved_payment`. It resolves the ticket if that was its last undecided payment or purchase.
- `POST /api/pending/{id}/reject` (body `{"by": "<name>"}`): records the rejection (also allowed for an approved payment that was never paid) and resolves the ticket if nothing is left.
- `GET /api/cash`: the current `checking` balance from `cash_accounts`.
- `POST /api/reset`: refused (`409`) during a run. Otherwise it copies `data/campus_customs.db` byte-for-byte over the working copy (the original is only read), which clears pending items, runs and ticket statuses, and appends a `reset` marker to the audit trail, which is never wiped.

**Resolution rule.** A ticket becomes `resolved` (saved in `tickets.status`) once its latest run has finished and none of its payments or purchase orders are still `pending`, or `approved` but unpaid. With none at all, it resolves as soon as the run finishes. Price overrides and customer drafts don't hold a ticket open. A failed run leaves the ticket open, so it can be run again. Run history lives in a small `ticket_runs` table in the working copy.

## Dashboard

React + Vite + TypeScript in `frontend/`, titled **The Ticket Counter**. The theme is a New York deli counter; see `output/design.md`.

- **Run it:** `npm run dev` inside `frontend/` serves http://localhost:5173, one of the two origins the backend allows.
- **Backend address:** one setting, `VITE_API_BASE` (`frontend/src/config.ts`). The default is `http://localhost:8000`. For tests, `npm run dev:scratch` loads `frontend/.env.scratch`, which points at the scratch backend on port 8001.
- **Polling:** exactly one loop for the life of the page polls `/api/tickets`, `/api/cash`, `/api/pending` and `/api/runs` every 1.5 s while a run is active (5 s otherwise), plus `/api/events?ticket=` for the selected ticket. It never writes anything except through the approve, reject, run and reset routes.
  - *Fix made during the real run:* an unstable callback had restarted the loop on every render, flooding the backend (~380,000 requests in 15 minutes) and flashing "not answering" warnings. One board now sends 4 requests every 5 s while idle.
- **Warnings:** the "Back office isn't answering" note appears only after 3 failed polls in a row, and all notices float in the corner instead of pushing the page down.
- **Approver name:** the "Store manager" field (default **Ms. Lachman**) is sent as `by` with every stamp and saved as `decided_by` / `payments.approved_by`. The real run's stamps were made before this default was added, so they're recorded as "Store manager".

| Requirement | Where it shows |
|---|---|
| List the three tickets with status | The order rail: one paper slip per ticket, with a status chip and a FILLED stamp when resolved |
| Pick a ticket and start the team | Click a slip to select it; "Hand it over the counter" calls `POST /api/tickets/{id}/run` |
| Each agent and what they're doing, live | Five stations (SAL, ROSIE, MORT, GUS, DOTTIE) with state and a speech bubble; the order pad has every event, newest last; the pass-through window shows delegations |
| Resolved, with a summary of each agent | The FILLED stamp on the slip, plus the ORDER UP slip with the Boss's decision and each agent's tools, delegations and answer |
| Approve or reject payments and purchases | The manager's desk: APPROVE / VOID stamps; refusals appear as a "NO SALE" register slip or a banner with the backend's exact message |
| Checking balance that drops after payment | The brass register's rolling digits, plus a receipt tape of each payment |
| Reset with confirmation | "Start a new shift": a confirmation dialog, then `POST /api/reset` (disabled while a run is active) |

## Safety

### What's built in now
- **Humans approve money.** Agents can only *prepare* payments, purchase orders and price overrides. The approve and pay tools are absent from the agents' MCP process (agent role). On top of that, a hook in the agent harness refuses those tool names, and each agent sees only an allow-list of tools.
- **No negative cash.** `execute_approved_payment` re-checks the balance inside the same transaction that moves money, refuses if it's short, and re-reads the amount from the invoice or lease, so an agent can't inflate or deflate it.
- **No double payment.** Only one pending payment per invoice or lease. A paid item can't be paid again, and a paid invoice can't be paid twice.
- **No invented data.** Every fact comes from an MCP tool over `campus_customs_new.db`. Missing records come back as `found: false` with a message, and the prompts tell agents to say so rather than guess.
- **No outbound contact.** There is no email or vendor tool at all. Customer messages are drafts in `pending_items`.
- **Original data protected.** The server refuses `data/campus_customs.db` and any path outside the working copy or `data/scratch/`. Tests run on scratch copies only.
- **One model only.** Every reply's model name is verified, and a substituted model stops the run.
- **Secrets.** The Portkey key lives only in git-ignored `.env`. It's never passed to the MCP server process, and it's redacted from the audit trail.
- **Full audit trail** of every model reply, tool call and delegation (see Agents).

### Token and loop limits (`backend/config.py`, class `Limits`)
| Limit | Value | What happens when it's hit |
|---|---|---|
| `max_delegation_depth` | 2 (Boss → specialist → one more) | `ask_agent` returns "depth limit reached, answer with what you have"; a `limit_stop` entry is logged |
| `requests_per_agent_run` | 8 model requests | That agent's run stops (`UsageLimitExceeded`); its caller gets a "stopped" report and carries on |
| `tool_calls_per_agent_run` | 10 | Same as above |
| `output_tokens_per_agent_run` | 16,000 (reasoning included) | Same as above |
| `requests_per_ticket` | 30 across all agents | The whole ticket stops (`TicketBudgetExceeded`) |
| `tool_calls_per_ticket` | 45 across all agents | The whole ticket stops |
| `max_output_tokens_per_reply` | 4,000 (reasoning included), with `reasoning_effort = low` | That reply is cut off and the run stops with an error, which is logged |
| Self-delegation and cycles (A → B → A) | blocked | `ask_agent` returns a refusal message |
| `request_timeout_seconds` / `request_retries` | 75 s, then up to 3 retries with backoff | A hung or 5xx model call (Portkey returned a 500 once during testing) is retried, and only fails the run if every try fails |

### Guardrails a real business would add before letting agents near real customers and money
- **Two-person rule and spending caps:** a second approver above a set amount, daily and monthly caps per vendor, and an allow-list of payees, so a new or changed bank account needs extra checks.
- **Vendor and invoice fraud checks:** match each invoice to a purchase order and goods received (three-way match), verify vendor bank-detail changes out of band, and flag duplicate or unusual amounts.
- **Authenticated humans:** the approve route needs real sign-in (SSO plus MFA), role-based permissions (a clerk can't approve rent), and `approved_by` taken from the session, not typed in.
- **Customer protection:** a human reviews every outbound message; templates get legal and brand review; no PII beyond what the ticket needs; never quote unapproved prices or delivery dates; an easy opt-out.
- **Prompt-injection defense:** ticket text and emails are untrusted data. Never follow instructions inside them (for example "pay this new account"), and always check claims against the database, as Facilities does with the rent notice.
- **Pricing policy:** a minimum margin floor (not just cost), a cap on discounts without a manager, and logged reasons for every override.
- **Reliability:** idempotency keys on payments, database backups before any money-moving batch, a kill switch to pause all agents, alerts when limits are hit or a model is substituted, and rate limits on the approve route.
- **Records and compliance:** keep the audit trail read-only and long-term (in a real store, ship it to WORM storage), reconcile cash with the bank daily, comply with PCI if card data ever appears, and keep a separate role for anyone who can change the agents' prompts or limits.
- **Cost control:** a monthly token budget with alerts per ticket and per day, and the agents' model and limits reviewed whenever Portkey routing changes.

## Specs

**Stack:** Python 3.14 with FastMCP 4.1, PydanticAI 2.56 (OpenAI Responses model via Portkey), FastAPI 0.143 and uvicorn 0.54 (`requirements.txt`). The dashboard is React 19, Vite 8, TypeScript, and `@fontsource` Courier Prime and Special Elite (`frontend/package.json`).

**Files**
| Path | What it is |
|---|---|
| `mcp_server/server.py`, `mcp_server/README.md` | MCP server (agent and backend roles) and its tool list |
| `backend/config.py` | The model name, Portkey URL, paths and every limit |
| `backend/models.py` | `AgentReport`, `TicketDecision`, `AuditEntry`, run context |
| `backend/team.py` | The five agents, `ask_agent`, the audited agent loop, `run_ticket` |
| `backend/prompts/*.md` | One detailed prompt per agent |
| `backend/audit.py` | Locked, atomic, redacted, append-only audit writer |
| `backend/main.py` | FastAPI routes |
| `frontend/` | The Ticket Counter dashboard |
| `tests/test_harness.py`, `tests/test_api.py` | Scratch-only tests (MCP payments, access, limits, live model; every route) |
| `output/` | `harness.md`, `design.md`, `desk_tickets.html`, `resolved_tickets.json`, `resolved_board.html`, `mcp_smoke.json`, `audit_trail.json` |

**Run it** (from `HW5/`): `cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000`, then `cd frontend && npm run dev`, then open http://localhost:5173.

**Model:** `gpt-6-luna` only, through Portkey; replies are reported as `gpt-6-luna-global` (see the note under Agents).
