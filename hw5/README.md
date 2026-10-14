# Campus Customs agents (HW5)

A team of five AI agents (Boss, Inventory, Accounting, Facilities, Customer Service) runs a fictional Yale merch shop, "Campus Customs". They work support tickets through an MCP server over a SQLite database. A human approves every payment on a React board called **The Ticket Counter**. Every agent uses only `gpt-6-luna` through Portkey.

Full design and details: [`output/harness.md`](output/harness.md) (tables, MCP tools, agents, API routes, dashboard, safety). Results of the real run: `output/desk_tickets.html`, `output/resolved_tickets.json`, `output/resolved_board.html`.

## What's in `data/`
- `data/campus_customs.db`: the **original**. Never modified.
- `data/campus_customs_new.db`: the **working copy** the agents use. In this repo it's in its **finished, resolved state** after the real run: tickets 101–103 resolved, checking at $160, 2 payments made.

For a clean run, start the working copy from the original. Either copy the file:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

or use the board's **Start a new shift** button, or `POST /api/reset`, once the backend is running (see below).

## Setup (from the `hw5/` folder)

1. **Secrets:** copy `.env.example` to `hw5/.env` and put your Portkey key in `PORTKEY_API_KEY`. `.env` is git-ignored; never commit it.
2. **Python packages** (built and tested on Python 3.14):
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
3. **Front-end packages** (built and tested on Node 24):
   ```bash
   cd frontend && npm install && cd ..
   ```

## Run

- **MCP server** (stdio). It's started for you by the backend for each run and by Claude Code via `.mcp.json`. To start it by hand:
  ```bash
  .venv/bin/python mcp_server/server.py
  ```
- **FastAPI backend** on port 8000:
  ```bash
  cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000
  ```
  Check it with http://localhost:8000/api/health.
- **React board (The Ticket Counter)** on port 5173:
  ```bash
  cd frontend && npm run dev
  ```
  Then open **http://localhost:5173**. The backend only accepts browser requests from `http://localhost:5173` and `http://127.0.0.1:5173`.

## A full three-ticket run

1. **Reset first:** click **Start a new shift** on the board (or `curl -X POST http://localhost:8000/api/reset`). This copies the original database over the working copy, which clears pending items, runs and ticket statuses. It's refused while a run is going.
2. **The audit trail is never wiped.** `output/audit_trail.json` only grows: a reset appends a `reset` marker, and the board shows events since the last marker.
3. On each ticket (101, 102, 103), click **Hand it over the counter** and watch the agents. Then stamp each pending payment or purchase **APPROVE** or **VOID** on the manager's desk. Only approved payments move cash. A ticket shows **FILLED** once its run has finished and nothing is waiting on you.

## Tests (scratch copies only)

```bash
.venv/bin/python tests/test_harness.py --offline
```

Leave off `--offline` to include the live model checks. `tests/test_api.py` expects a backend started on port 8001 with `CAMPUS_CUSTOMS_DB` and `CAMPUS_CUSTOMS_AUDIT` pointing into `data/scratch/`.
