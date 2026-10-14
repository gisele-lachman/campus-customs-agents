# Campus Customs — AI Prompt Log

## Problem 1: Vibe coder prompts

Hello there! We're working on this new project, one step at a time, so keep it separate from anything we've done before, and don't change anything outside this folder (hw5). The project is a team of AI agents that runs a fictional Yale merch shop called "Campus Customs," plus a website to watch them work. I'll give you one problem at a time, so only do what I ask in each message and don't jump ahead.

Ground rules for the whole project:
- The shop database is data/campus_customs.db. That original must never be changed; later we'll make a working copy.
- I don't want to type in a terminal. Do all installing, starting servers, and testing yourself.
- Never stop or kill a process unless you started it in this session and know its exact process id. Never kill by name or pattern, or touch parent or system processes. If unsure how to restart something safely, ask me.
- The agents use a Portkey API key, kept only in a .env file that stays out of GitHub. Never write it anywhere else, print it, or log it. A key from an earlier project may be in a neighboring folder, but ask me before copying it.
- Every agent must use only the model gpt-6-luna through Portkey. No other model name may appear anywhere in code, comments, settings, or docs, not even as a default. Portkey silently substitutes a different model if it doesn't recognize a name, so when we get there, verify which model actually replied.

First task: I have to log everything I type to you. Create AI_prompts.md in the main hw5 folder with a short title, then one section per problem (number and title). Start with "Problem 1: Vibe coder prompts" and put this message in it, word for word. If I send a follow-up because your first answer was missing something, log it too, with one sentence on what was lacking.

From now on, at the start of each problem, add its section and paste my message exactly as written. Use the title I give, or make up a short one and tell me. Replace any secret in my messages with [REDACTED].

When done, show me the file, and confirm where data/campus_customs.db is without moving it. Don't build anything else yet.

## Problem 2: Study the Campus Customs database

Excellent. Now, on to Problem 2, titled "Study the Campus Customs database". Please add its section to AI_prompts.md first, with this message pasted in exactly.

Please look through every table in data/campus_customs.db and every field in each, read-only. Then copy the file to data/campus_customs_new.db. That copy is the working database for the rest of the project, and the original must stay untouched, so afterwards confirm the original's checksum still matches and the copy is identical to it.

Then study the three open tickets (101, 102, 103). For each, trace how it links to other tables (for example sku/size to inventory and pricing, invoice_id to invoices and vendors, lease_id to leases) and what facts it would need. Here are the shop's rules, which will matter:
- desk.date_today is "today" for the shop; use it to decide what's overdue or due soon.
- Vendor lead times come from the vendors table.
- A vendor won't ship new product while they have an open unpaid invoice.
- Any payment needs human approval, and when a payment is made, the relevant tables must be updated.
- If there isn't enough cash, a payment must be refused (no negative balances).
- Cash only goes out; no revenue is modeled.
- Nobody gets emailed and no real vendor is called; drafts stay on the board.

Now start output/harness.md (create the output folder if needed). For each table, list its fields with one short line on why the table matters for the agents. Then add a short section on the three tickets and how each links to the other tables, and a section with the shop rules above. At the bottom, add empty headings for the parts we'll fill in later: MCP tools, Agents, API routes, Dashboard, Safety, and Specs.

When you're done, give me a real quick summary: each table and its row count, what each ticket needs, and anything in the data that looks tricky or that could block a ticket (such as a cash shortfall or an unpaid invoice). Don't build anything else yet.

## Problem 3: Build the MCP server

Very nice very nice. Now, on to Problem 3, titled "Build the MCP server". Please add its section to AI_prompts.md first, with this message pasted in exactly.

Please write an MCP server using FastMCP, in the folder mcp_server/ (the file is mcp_server/server.py). It reads data/campus_customs_new.db, the working copy, and never the original. Every agent in this project will use these tools later, and we'll add more in a later problem, so for now write three read-only tools that I know I'll need for the tickets. Here's my suggestion, but use your judgment on the exact names and details, as long as they're clear:
1. A stock check by sku and size (inventory table), which helps ticket 101 (is size S in stock?) and ticket 103 (are 20 hoodies in size M available?).
2. A vendor and invoice check (invoices and vendors tables), which helps ticket 101 (is the vendor blocked by an unpaid invoice, how overdue is it compared to desk.date_today, and what's the lead time?).
3. A rent status check by lease id (leases table, plus desk.date_today), which helps ticket 102 (how much is due, when, and how many days away is that?).

The rules for the tools:
- Never invent data. Everything comes from the database, and if something isn't found, say so clearly instead of guessing.
- Use clear names, simple inputs, and short, structured results. Compute simple things like days overdue or days until due using desk.date_today as "today".
- These three must be strictly read-only. Open the database in read-only mode and use safe queries.
- Since the original database must stay untouched, make sure the server only points at campus_customs_new.db.

Also be sure to:
- Add the needed packages to requirements.txt in the main folder, and install them yourself.
- Write mcp_server/README.md: what the MCP server is for, which database file it uses, and the three tools it has.
- Fill in the "MCP tools" section of output/harness.md. For each tool, list which table it reads, which ticket it helps unlock (101, 102, or 103), and one sentence on why that tool is the right one for that ticket. Be specific and tie each tool to its ticket, since vague lines like "reads inventory" score low.

I don't need you to connect or run the server as a server yet (that's actually the next problem). But you can test each tool directly by calling its function against the working copy, and compare each result to the database. Then tell me what each tool returned. Then please check that the original database's checksum is unchanged, and don't build anything else yet.

## Problem 4: Add the MCP server to the vibe coder and test each tool

On to Problem 4, titled "Add the MCP server to the vibe coder and test each tool". Please add its section to AI_prompts.md first, with this message pasted in exactly.

This is the first part of Problem 4. Please connect our MCP server to Claude Code for this project. Save the connection in .mcp.json at the main hw5 folder. This file goes to GitHub, so use relative paths (no absolute paths with my username), no secrets, and the server's standard stdio setup. Check that the server starts and answers properly using a quick test process you start yourself, stop it only by its exact process id, and make sure the original database is untouched.

Then create a short CLAUDE.md in hw5 with the ground rules from my first message, so they carry over to a fresh session: this project lives only in hw5; the original data/campus_customs.db is never changed and we work on data/campus_customs_new.db; I don't type in a terminal; process-safety rules (only stop processes you started, by exact id, never by name or pattern); the Portkey key lives only in .env, never printed or written elsewhere; and every agent uses only gpt-6-luna. Also add: log each of my messages in AI_prompts.md word for word, and do one problem at a time. Don't put any secret in it.

Finally, tell me exactly what I need to do so your session can see the new server (for example, quitting and reopening Claude Code), in plain steps. Please don't run the tool tests yet, and don't build anything else.

### Follow-up (Problem 4)

Which MCP tools do you have?

*What was lacking:* after reopening Claude Code, we still needed to confirm that the session could actually see the campus-customs MCP server and its tools.

### Prompt 2 (Problem 4)

After you confirm that you can see our MCP server and its three tools, answer these three questions by actually calling the MCP tools through the connection (not by reading the database or importing the Python code yourself):
1. Is there a size S Classic Bulldog Tee (CC-TEE-WHITE) in stock for ticket 101's request for 1?
2. Is Bulldog Print Co blocked from shipping because of invoice 501, and how overdue is it?
3. How much is the Chapel Street shop's rent, and how many days until it's due?

Save the evidence in output/mcp_smoke.json. For each of the three tests include: the exact question above as the prompt, the tool name, and the tool's actual output. Then check every output against data/campus_customs_new.db yourself, read-only, and tell me whether they match. Confirm the original database's checksum is unchanged. If you can't see the MCP tools, tell me what you see instead of working around it. And don't build anything else yet.

## Problem 5: Build the agent team and grow the MCP tools

Looking good looking good. Let's move forward to Problem 5, titled "Build the agent team and grow the MCP tools". Please add its section to AI_prompts.md first, with this message pasted in exactly.

Build the Campus Customs agent team with PydanticAI, five agents:
- Boss: reads each ticket, decides who works on it, and makes the final call.
- Inventory: checks stock by SKU and size, spots shortfalls, and works out which vendor can restock (blocked or not, and how long it takes).
- Accounting: watches cash and invoices, checks margins, and prepares payments and purchase orders for human approval.
- Facilities: leases and rent.
- Customer Service: drafts messages to customers.

How they should work:
- Full connectivity: any agent can delegate to any other agent and get an answer back. Keep token use in check and prevent endless loops with limits in one place (delegation depth, tool calls, model requests per agent run and per ticket).
- Every agent uses only gpt-6-luna through Portkey. Set up .env (ask before copying my earlier key), .env.example with placeholders, and .gitignore for .env.
- Shop facts come only from our MCP server over data/campus_customs_new.db, with no second tools layer around it. Agents get the MCP tools plus delegation, nothing else.

Files: one detailed prompt per agent in backend/prompts/ (boss.md, inventory.md, accounting.md, facilities.md, customer_service.md), data types in backend/models.py, and agent code under backend/. Detailed prompts score higher, so for each agent cover its scope, the shop rules it needs, who to ask for what, which tools to use, what to report back, and what it must never do (invent data, email customers, call vendors; drafts only).

Grow the MCP server with whatever tools the agents need for tickets 101, 102 and 103 (for example cash balance, ticket details, pricing and margin, vendors, and tools to prepare a payment, a purchase order, and a customer message). Rules:
- Agents only PREPARE payments and purchase orders as pending items for a human. The tool that actually pays works only on a human-approved item, refuses if cash is short (no negative balance), and updates the tables properly (payments, cash, and the invoice or lease). Agents must not have access to that tool, since only the backend's approve route will use it later.
- You may add a small table for pending items and drafts to the working copy only. The original stays untouched.
- Record your choices in output/harness.md (like the payment "kind" and "ref_id" values, and what each payment updates).

Regarding Audit trail: every agent-loop step appends to output/audit_trail.json: time, ticket, agent, step type (model reply, tool call, delegation), tool name, short args and result, stop reason, and the model that replied. Never wipe it, keep it safe from crashes and simultaneous writes, and keep secrets out.

Docs: in output/harness.md, list each agent and each MCP tool with the table it uses, and add a Safety section covering guardrails a real business would want when agents touch real customers and money, plus the token limits. Update mcp_server/README.md to match the tool list.

Test on scratch copies only (scratch database and audit file), so the working database and real audit trail stay clean. Check that the model that actually replied is gpt-6-luna, delegation works between at least two agents, limits stop a runaway loop, a payment without approval or without enough cash is refused, and agents can't reach the pay tool. Confirm the original database's checksum is unchanged and tell me what you found. Don't build the routes, dashboard, or run the real tickets yet.

## Problem 6: Plan the three tickets

Thanks for that. On to Problem 6, titled "Plan the three tickets". Please add its section to AI_prompts.md first, with this message pasted in exactly.

Before we run, I want a written plan of what I expect the team to do on each open ticket. Please build output/desk_tickets.html, a single self-contained page I can double-click open (no server, no internet needed), with these tabs: Ticket 101, Ticket 102, Ticket 103, Cash, and Reflection. The Cash and Reflection tabs just need a short "coming later" note for now.

Each ticket tab should have:
- A short summary at the top of the ticket (who asked, what for, and the key facts from the database, like stock, cost, due dates, and cash), using real data only.
- An "Expected" section with: (1) who the Boss should call first and why; (2) every delegation I expect, in order, with the reason for each; (3) which MCP tools I expect the run to use; and (4) what I expect to end up needing human approval, and any problems I expect (for example, the vendor being blocked, or not enough cash).
- An empty "Actual" section with a short placeholder saying it will be filled in after the real run, laid out so it's easy to fill in later next to the Expected one (who worked, what they delegated, which tools).

Plans that send every agent to every ticket score low, so reason from the data about who is really needed on each ticket and say which agents I do NOT expect to be involved, and why. Base the plan on the shop rules, the ticket data, and the tools we built. Don't run any agents, and don't peek at any earlier test output to write it, since this is a prediction I'll compare against the real run.

Keep the page simple and clean, and make sure the tabs work when opened straight from the file.

Two other small items:
1. Add a short note to output/harness.md explaining that Portkey reports the model as "gpt-6-luna-global" (the Azure name for gpt-6-luna), so a grader doesn't mistake it for a different model.
2. Make sure .gitignore keeps data/scratch/ and any other test or scratch files out of GitHub (the two real databases will be included in the repo later).

Please open the finished page from the file to check that every tab shows, and tell me what you planned for each ticket.

## Problem 7: Backend routes

Great. 

On to Problem 7, titled "Backend routes". Please add its section to AI_prompts.md first, with this message pasted in exactly.

Build the FastAPI backend in backend/main.py, startable from inside backend/ with: uvicorn main:app --reload --port 8000. Allow only the browser origins http://localhost:5173 and http://127.0.0.1:5173. Routes:
1. List the three tickets with open or resolved status, plus subject and requester.
2. Run the agent team on a ticket id. It starts in the background and returns right away so the dashboard can poll. Allow one run at a time and refuse resolved tickets. A ticket becomes resolved once its run has finished and every pending payment or purchase from it is approved or rejected (immediately if there are none). Save the status in the working database's tickets table, and add a way to check a run's status.
3. Return recent agent events, newest last (what each agent said, which tools they used), from output/audit_trail.json, optionally filtered by ticket.
4. Approve or reject a pending payment or purchase, plus a route listing pending items. Agents only prepare payments; the approve route is what actually changes cash. It records the human's approval, then uses the human-only MCP tools to pay, refuses if cash is short (no negative balance) with a clear message, and resolves the ticket if that was its last pending item.
5. Return the current checking balance from cash_accounts.
6. Reset: restore data/campus_customs_new.db from data/campus_customs.db (clearing pending items and ticket statuses), never modifying the original, and refuse during a run. The audit trail must never be wiped, so write a "reset" marker into it and have the events route show only events since the last reset.

Agent runs use the agent-side MCP role; only approve/reject use the human-only tools. List the routes, one line each, in the "API routes" section of output/harness.md.

Test on the scratch database and audit file so the real ones stay clean. Start the backend yourself and stop it only by its process id. Check every route, including one real ticket run on scratch with events appearing as it goes, approve, reject, a refused payment without enough cash, an approval that resolves a ticket, reset (original checksum unchanged), and a blocked request from another origin. When done, confirm the working database still matches the original and the real audit trail has no test entries, then leave the backend running on port 8000 against the real working database. Tell me what you found, and don't build the dashboard yet.

## Problem 8: Agent dashboard

Moving on to Problem 8, titled "Agent dashboard". Please add its section to AI_prompts.md first, with this message pasted in exactly.

Build the dashboard in frontend/ with React + Vite + TypeScript. It calls our backend at http://localhost:8000 (keep the address in one setting I can override for testing). At minimum it must:
- List all three tickets with their status.
- Let me pick a ticket and start the agent team on it.
- Show each agent and what they're saying or doing while it runs (poll the events route).
- Mark the ticket resolved when done, and show a short summary of what each agent did.
- Let me approve or reject each pending payment or purchase, with a clear message if the backend refuses.
- Show the checking balance, updating so I can see it drop after an approved payment.
- Include a reset button for a fresh run, with a confirmation first.

USE THIS DESIGN CONCEPT: a New York deli counter. The idea is handing your ticket over the counter and getting your order back, a cute play on the tickets situation. Vintage, nostalgic, and fun to use, and it should feel like one cohesive place, not a pile of effects.
- Fonts: a typewriter look that is still easy to read. Use a clean typewriter face (like Courier Prime or similar) for body text, and keep any rougher, stamped or distressed styling for headings and stamps only. Bundle the fonts with the app (e.g. via npm font packages) so it works offline.
- Colors: muted greens (think deli tile), maroons and navy, with gold and silver accents, on cream or butcher-paper backgrounds. Keep text contrast easy to read.
- Tickets are paper order slips (perforated edges, ticket numbers, maybe on a rail or spindle). Resolved tickets get a satisfying "FILLED" or "ORDER UP" stamp.
- The five agents are the staff behind the counter, each at a station with their own look (name tag, color, badge, personality in how their lines read), so you can tell them apart at a glance. Show delegation as slips being passed from one station to another, with a clear trail of who handed work to whom.
- Approving is a manager's stamp ("APPROVED") and rejecting a "VOID" stamp. A refused payment should read like the register refusing, with a clear message.
- Cash is an old brass cash register display with rolling digits that visibly drops after a payment, plus a paper receipt tape listing each payment.
- Reset is "start a new shift" and needs a confirmation.
- Optional touches: a "now serving" number display, a counter bell sound (off by default, with a mute toggle), subtle paper textures. Add any other details that tie the idea together.
- Handle loading, errors, empty states and long waits gracefully, and make it work at laptop width. Draw all graphics yourself.

Write output/design.md covering what you chose (layout, how agents read differently, how resolved tickets and cash show up) and why, including the creative choices that make it feel special and enjoyable. Keep it concrete and short. Also fill in the "Dashboard" section of output/harness.md.

Test against a scratch backend on port 8001 (scratch database and audit file; note its process id and stop it only by that id) with the dashboard pointed at it, so the real database and audit trail stay clean. In a real browser, run one ticket through the whole flow on scratch: start, watch agents live, approve, see the balance drop, see it resolve, and reset. Look at screenshots and fix anything off, like cut-off text or hard-to-read colors. At the end, make sure the default address is http://localhost:8000, start it with npm run dev (leave it running on port 5173), and confirm the original database and real audit trail are untouched. Don't run the real tickets yet. Tell me what you checked and anything you couldn't verify.

## Problem 9: Resolve the tickets

Yes! This looks awesome. Let's do Problem 9, titled "Resolve the tickets". Please add its section to AI_prompts.md first, with this message pasted in exactly, and remember, this is the real run, so no shortcuts.

Setup: reset data/campus_customs_new.db with the backend's reset route and confirm it matches the original. Note the starting checking balance. Make sure the backend (port 8000) and the dashboard (port 5173) are running. The real audit trail is appended to, never wiped.

The run: run tickets 101, 102 and 103 in that order through the board until each is resolved. I'm the human approver. Whenever an agent has prepared a payment or purchase, stop, tell me exactly what's waiting (ticket, what, amount, cash left if approved), and wait for me to approve or reject it in my own browser at http://localhost:5173. Never approve or reject anything yourself and never call the human-only tools. If a payment is refused for lack of cash, tell me and wait for my decision (for example, rejecting it so the ticket can resolve). If a run fails or stops early, retry it and record that honestly. When each ticket resolves, take a screenshot of the board showing it (FILLED, order pad, summary, cash).

Then fill in the results:
1. output/desk_tickets.html: on each ticket tab, fill in the Actual section from the real run (which agents worked, what they delegated, which tools they used). Don't change the Expected sections, since I'll compare them. On the Cash tab, itemize: the starting balance after reset; for each ticket, how cash changed when it resolved and why (which payment or purchase, dollar amount); and the ending balance. Check the ending balance against cash_accounts in the working database and show me the arithmetic.
2. output/resolved_tickets.json: for each ticket, the id, final status, short outcome, what each agent contributed, and the human approvals.
3. output/resolved_board.html: a double-clickable page with a screenshot of the React board for each resolved ticket (101, 102, 103), each with a heading and a one-line caption. Embed the images so it's one self-contained file.
4. Finish output/harness.md so it covers the tables, MCP tools, five agents, API routes, dashboard and safety rules, and fix anything outdated.

At the end, confirm the original database is unchanged, the audit trail has the real runs and a reset marker, and every payment is in the payments table. Tell me broadly how Actual compared to the plan, but don't edit the plan.

### Follow-up (Problem 9)

Okay I approved #1 and #2, so you can go ahead and check the results. Also, I few things I noticed from using the platform: The Store Manager label at the top, we can say that I [Ms. Lachman] am the store manager; The pop-up notification that occurs when the agents are not responding is much too frequent, it causes the page to jump around too much, let's reduce the frequency of this message when this problem happens; The numbers on the knobs below the checking balance are not in ascending order (they being with 7, they should begin with 1); The name of the site should not be "Campus Customs Deli," it's too on the nose, let's change to something that sticks with the theme but makes more sense regarding the function of this platform.

*What was lacking:* using the board for real showed the manager name was generic, the "not responding" banner flashed too often and shifted the page, the register keys were out of order, and the site name didn't describe what the board does.

## Problem 10: Reflection

Nice work. Now, on to Problem 10, titled "Reflection". Please add its section to AI_prompts.md first, with this message pasted in exactly (including the reflection below).

Fill in the Reflection tab of output/desk_tickets.html. Leave the Expected sections, Actual sections and Cash tab exactly as they are, and make sure the page still works when double-clicked. Below is my own personal reflection. Use it as the base: check every number and claim against output/audit_trail.json, output/resolved_tickets.json, the Actual and Cash tabs and the working database, and correct anything that's wrong. Then add specifics and evidence where my answers are thin (exact step counts, durations, tool names as they appear in our MCP server, which agents did what), while always keeping my points and my voice. Make it organized by the five questions, with references to the ticket tabs and Cash tab as evidence. Don't invent facts. Afterwards, open the page from the file to check every tab, and tell me what you corrected and what you added.

My Personal Reflection:

How I'd evaluate the agents: I'd judge each ticket on the same six things: (a) did the facts come straight from the database, (b) were the shop rules followed (vendor blocked by an unpaid invoice, no negative cash, nothing sent to customers), (c) was human approval respected, (d) is the cash math right, (e) were the right agents used without wasted effort, and (f) how much time and how many steps it took.
- Ticket 101 (Bulldog tee, size S) went best. Inventory found 0 in size S, the vendor check showed Bulldog Print Co blocked by invoice 501 ($840, 3 days overdue), and Accounting prepared the payment. Nothing moved until I approved, and cash went from $3,400 to $2,560. The weak spot was an extra $8 purchase order for 1 tee, which was probably redundant because invoice 501 was already for a rush reprint of that exact tee. It took about 4.75 minutes.
- Ticket 102 (rent) was the cleanest. The tools showed $2,400 due 2026-09-02, two days out. The Boss called Facilities and Accounting, prepared one payment, I approved it, cash went to $160, and the lease's next due date moved to 2026-10-02. Inventory and Customer Service correctly stayed out.
- Ticket 103 (Yale AI Club hoodies) was the weakest. It ended in "needs more info" with no discount and no purchase order, and the only output was a draft asking the club for a target price. That didn't break any rules and nothing was made up, but it didn't really solve what the club asked, and the ticket still counted as resolved while the question was open. There was also a mix-up: when Accounting double-checked with Inventory, the stock check was run for 12 hoodies instead of 20 (so it said "short 4"), while Inventory still reported the correct shortfall of 12 (8 on hand vs. 20 requested), and the Boss treated the two numbers as a conflict. It was also the longest run, about 7 minutes.

Actual vs. Expected:
- 101: the first call (Inventory) and the delegations I predicted (Inventory, Accounting, Customer Service) all happened, and I'd correctly flagged that the 1-tee purchase order might be redundant, and it was prepared anyway. What I didn't predict was Accounting asking Inventory to double-check. I also voided the customer draft instead of leaving it.
- 102: I'd predicted Facilities first, and listed the Boss calling Accounting directly as a plausible alternative. That's what happened, with Facilities and Accounting called in the same step. The agents I expected to stay out stayed out.
- 103: the biggest difference. I expected a price override, a $264 purchase order for 12 hoodies from a blocked vendor, and a cash problem ($840 + $2,400 + $264 = $3,504 vs. $3,400). Instead, by the time 103 ran, I'd already paid invoice 501 on 101, so the vendor wasn't blocked anymore, and the Boss asked for a price instead of proposing a discount. No restock was prepared, so the shortfall never showed up. Even so, with only $160 left after the invoice and rent, a $264 order would have been refused for lack of cash. The lesson: the tickets aren't independent, since what happens on one (paying 501) changes what's possible on the next.

What would have been simpler as one agent with tools: Ticket 102 is three lookups in a row (the lease, the cash balance, then prepare the payment), and ticket 101 is a straight chain: check stock, check the vendor, pay the invoice. One agent with the same tools could have done both with far less delegation, in less time. The 103 stock mix-up came from a handoff: the question changed in transit (12 instead of 20) and the Boss then had to reconcile two numbers. A single agent holding the ticket would have read the quantity once. The team did do some things better: only Accounting prepares payments, Customer Service only drafts, and the pay tool is reachable only from the human approval route; each agent has a narrow prompt, the audit trail shows who did every step, and the Boss acts as a final check. For a shop this small I'd probably use one agent plus the same tools and keep the human approval gate, and use a team only where separate responsibility matters, like money and customer messages.

Three new problems this team could solve with the tools we built:
- A new unpaid vendor bill, like another Elm City Gifts invoice: the invoice and vendor tools show what's owed and whether the vendor is blocked, Accounting prepares the payment, and I approve it (tables: invoices, vendors, payments, cash_accounts).
- A customer asking for the Crest Mug, which has 0 in stock: Inventory checks stock, Elm City Gifts is the vendor (3-day lead time), Accounting prepares a purchase order at the $3.50 unit cost, and Customer Service drafts a reply with the expected date (tables: inventory, vendors, pricing).
- A discount request that names a price, like 103 if the club had said what it would pay: Accounting checks the offer against the pricing table (hoodie cost $22, list $58), Inventory checks stock, and Customer Service drafts the answer (tables: pricing, inventory).

Three new problems this team could not solve, and what I'd add:
- The issue with future cash. We ended with $160, and the next $2,400 rent is due 2026-10-02, but we never modeled revenue, so the team can't see money coming in. I'd need a sales and receipts table, a tool to record a sale or payment received, a cash forecast tool (upcoming rent, invoices, expected sales), and a Treasury agent that recommends which bills to pay first or delay.
- Actually contacting people. The draft to Tauhid Zaman (101) and the question to the Yale AI Club (103) never went anywhere, and tickets only store a requester's name, not an email. I'd need a customer contacts table, a send-email tool that needs my approval first, an inbox-reading tool so a reply can reopen a ticket like 103, and an Outreach agent to track replies.
- Receiving stock. Approving the purchase order on 101 only records it; nothing updates inventory when the tee arrives (around 2026-09-05), and there's no order status or delivery tracking. I'd need a purchase order status table, a receive-shipment tool that updates inventory (with a human check), and a Receiving agent that follows lead times and flags late deliveries.

## Problem 11: Submit to GitHub

This is the last problem, Problem 11, titled "Submit to GitHub". Please add its section to AI_prompts.md first, with this message pasted in exactly.

Put the project on GitHub in a new public repository called campus-customs-agents, with everything inside one folder named hw5 (lowercase): AI_prompts.md, requirements.txt, .env.example, .gitignore, .mcp.json, README.md and CLAUDE.md at the top; data/ with BOTH campus_customs.db (the original) and campus_customs_new.db (the working copy, in its current finished state); mcp_server/, frontend/ (with package-lock.json), backend/ (including prompts/), tests/, and output/ (harness.md, mcp_smoke.json, desk_tickets.html, design.md, resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt).

Keep out: any .env file (my real Portkey key must never go online), data/scratch/, node_modules, .venv, caches, build output, logs, pid files, lock and scratch files. Don't turn the folder above this one into a git repository.

The Steps:
1. Make a clean copy of just the repo files in a new folder outside my project folder, and leave my working folder alone.
2. Make sure .env.example has placeholders only for every setting the app reads, and .mcp.json uses relative paths with no username or secrets. Write a short README.md, matching harness.md, covering: copying the original database to the working copy for a clean run (and that the repo's working copy is in its finished, resolved state); where to put .env; installing the Python and front-end packages; starting the MCP server, the FastAPI backend, and the React board (and what address to open); and resetting the database before a full three-ticket run (the audit trail is never wiped).
3. Before anything goes online, scan every file to be committed for secrets and for any model name other than gpt-6-luna. Show me the file list and scan results, then WAIT for my OK.
4. After my OK, check what GitHub access this computer has (the GitHub command line tool or an existing login), then create the public repo and push. If you need me to log in, give me the simplest steps and wait. Put the repo URL in output/github_url.txt and push that as a second commit.
5. Verify like a grader: clone the public repo fresh into a temporary folder, add a copy of my .env there (never committed), and follow the README. Confirm the packages install from requirements.txt (a missing one is the bug I'm worried about), the MCP server starts, the backend starts on a port different from my running servers and returns the right tickets and balance, reset works, the front end installs and builds, and one tiny model call shows the key works and gpt-6-luna replies. Don't run a full ticket. Stop only processes you started, by exact process id, and delete only that temporary folder.
6. Tell me the repo URL, and confirm that AI_prompts.md in the repo has a section for every problem from 1 to 11 with at least one prompt, both database files are in, and no secrets are.

### Follow-up (Problem 11)

OK

*What was lacking:* the user approved the file list and the scan results so the push could go ahead.
