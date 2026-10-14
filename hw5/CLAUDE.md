# Campus Customs (HW5): ground rules

A team of AI agents runs a fictional Yale merch shop, "Campus Customs", with a website to watch them work.

- **Stay in this folder.** The whole project lives in `HW5/`. Don't change anything outside it, and keep it separate from earlier projects.
- **Database.** Never change the original `data/campus_customs.db`. All work uses the copy `data/campus_customs_new.db`.
- **No terminal for the user.** Do all installing, server starting and testing yourself.
- **Process safety.** Only stop processes you started in this session, by their exact process id. Never kill by name or pattern, and never touch parent or system processes. If unsure how to restart something safely, ask.
- **Secrets.** The Portkey API key lives only in `.env`, which stays out of GitHub. Never print it, log it, or write it anywhere else. Ask before copying a key from a neighboring folder.
- **Model.** Every agent uses only `gpt-6-luna` through Portkey. No other model name may appear anywhere in code, comments, settings or docs. Portkey silently substitutes unknown names, so verify which model actually replied.
- **Prompt log.** Log every user message word for word in `AI_prompts.md`, with one section per problem (number and title), and replace secrets with [REDACTED]. Log follow-ups too, with one sentence on what was lacking.
- **One problem at a time.** Do only what the current message asks; don't jump ahead.

MCP server: `mcp_server/server.py`, connected through `.mcp.json`.
