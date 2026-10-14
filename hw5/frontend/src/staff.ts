import type { AuditEvent } from "./api";

export type AgentKey = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";
export const AGENT_KEYS: AgentKey[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];

export interface Staff {
  key: AgentKey;
  name: string; // name tag
  role: string; // station sign
  station: string; // where they stand
  color: string; // apron / tag colour
  ink: string; // readable text colour on cream
  greet: string; // how they pick up a slip
  signoff: string; // how they hand it back
}

export const STAFF: Record<AgentKey, Staff> = {
  boss: {
    key: "boss", name: "SAL", role: "The Boss", station: "Head of the counter",
    color: "#1f3a5f", ink: "#1f3a5f",
    greet: "Order in!", signoff: "Order up.",
  },
  inventory: {
    key: "inventory", name: "ROSIE", role: "Inventory", station: "Stock room",
    color: "#3f6b4e", ink: "#2f5a3d",
    greet: "Lemme check the back.", signoff: "That's what's on the shelf.",
  },
  accounting: {
    key: "accounting", name: "MORT", role: "Accounting", station: "The books",
    color: "#722f37", ink: "#722f37",
    greet: "Per the books…", signoff: "Numbers don't lie.",
  },
  facilities: {
    key: "facilities", name: "GUS", role: "Facilities", station: "The building",
    color: "#7a5a12", ink: "#6b4e0e",
    greet: "Building's my beat.", signoff: "Roof's still over our heads.",
  },
  customer_service: {
    key: "customer_service", name: "DOTTIE", role: "Customer Service", station: "Front window",
    color: "#4a5568", ink: "#3b4454",
    greet: "Hon, I'll write 'em something nice.", signoff: "Draft's on the board, sugar.",
  },
};

export function staffOf(agent: string): Staff | null {
  return (STAFF as Record<string, Staff>)[agent] ?? null;
}

// What each MCP tool looks like from behind the counter.
const TOOL_VERBS: Record<string, string> = {
  get_ticket: "Read the order slip",
  list_tickets: "Glanced at the rail",
  check_stock: "Checked the shelf",
  list_vendors: "Flipped through the vendor card file",
  check_vendor_invoice: "Pulled the vendor's invoice",
  get_pricing_margin: "Ran the numbers on the price",
  get_cash_balance: "Peeked in the till",
  check_rent_status: "Checked the lease",
  list_pending_items: "Checked the spike for waiting slips",
  prepare_payment: "Wrote up a payment slip for the manager",
  prepare_purchase_order: "Wrote up a purchase order (not sent)",
  prepare_price_override: "Penciled in a price for the manager",
  prepare_customer_message: "Drafted a note for the customer (not sent)",
};

export function toolVerb(tool: string | null): string {
  if (!tool) return "Did something";
  return TOOL_VERBS[tool] ?? tool.replace(/_/g, " ");
}

/** Pull a field out of a JSON-ish string that the audit trail may have cut at 300 characters. */
export function pluck(text: string | null, field: string): string | null {
  if (!text) return null;
  const m = text.match(new RegExp(`"${field}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`));
  return m ? m[1].replace(/\\"/g, '"').replace(/\\n/g, " ") : null;
}

/** A short, human summary of a tool result. */
export function resultGist(e: AuditEvent): string | null {
  const r = e.result ?? "";
  if (!r) return null;
  const fields: [string, (v: string) => string][] = [
    ["message", (v) => v],
    ["note", (v) => v],
  ];
  const num = (f: string) => {
    const m = r.match(new RegExp(`"${f}"\\s*:\\s*(-?[\\d.]+|true|false)`));
    return m ? m[1] : null;
  };
  switch (e.tool_name) {
    case "get_ticket": {
      const subj = pluck(r, "subject"), who = pluck(r, "requester");
      if (subj) return `"${subj}" for ${who ?? "?"}`;
      break;
    }
    case "list_tickets": {
      const n = num("count");
      if (n !== null) return `${n} on the rail`;
      break;
    }
    case "list_pending_items": {
      const n = num("count");
      if (n !== null) return n === "0" ? "spike's empty" : `${n} slip${n === "1" ? "" : "s"} on the spike`;
      break;
    }
    case "list_vendors": {
      const names = [...r.matchAll(/"name":"([^"]+)"/g)].map((m) => m[1]);
      const blocked = (r.match(/"blocked":true/g) ?? []).length;
      if (names.length) return `${names.join(", ")}${blocked ? ` (${blocked} blocked)` : ""}`;
      break;
    }
    case "check_stock": {
      const q = num("qty_on_hand"), s = num("shortfall");
      if (q !== null) return `${q} on hand${s && s !== "0" ? `, short ${s}` : ""}`;
      break;
    }
    case "get_cash_balance": {
      const b = num("total_balance"), w = num("payments_awaiting_human");
      if (b !== null) return `$${Number(b).toLocaleString()} in the till${w && w !== "0" && w !== "0.0" ? `, $${Number(w).toLocaleString()} waiting on the manager` : ""}`;
      break;
    }
    case "check_rent_status": {
      const a = num("amount_due"), d = num("days_until_due"), due = pluck(r, "next_due");
      if (a !== null) return `$${Number(a).toLocaleString()} due ${due ?? "?"} (${d} days)`;
      break;
    }
    case "check_vendor_invoice": {
      const a = num("amount"), o = num("days_overdue"), b = num("vendor_blocked");
      if (a !== null) return `$${Number(a).toLocaleString()}, ${o} days overdue${b === "true" ? ", vendor BLOCKED" : ""}`;
      break;
    }
    case "get_pricing_margin": {
      const c = num("unit_cost"), l = num("list_price");
      if (c !== null) return `cost $${c}, list $${l}`;
      break;
    }
    case "prepare_payment":
    case "prepare_purchase_order":
    case "prepare_price_override":
    case "prepare_customer_message": {
      const id = num("item_id"), ok = num("prepared");
      if (ok === "true") return `slip #${id} on the spike, waiting for the manager`;
      const msg = pluck(r, "message");
      if (msg) return `didn't go through: ${msg}`;
      break;
    }
  }
  for (const [f, fmt] of fields) {
    const v = pluck(r, f);
    if (v) return fmt(v);
  }
  if (/^[[{]/.test(r.trim())) return null; // raw data: the verb already says what happened
  return r.length > 120 ? r.slice(0, 119) + "…" : r;
}

/** Plain-language version of a backend/model error, keeping the raw text for a tooltip. */
export function friendlyError(raw: string | null | undefined): string {
  const t = raw ?? "";
  const http = t.match(/status_code:\s*(\d{3})/);
  if (http && http[1].startsWith("5")) return `The model service had a hiccup (HTTP ${http[1]}). Nothing was lost; hand the ticket over again.`;
  if (/UsageLimitExceeded|TicketBudgetExceeded/.test(t)) return "Hit a safety limit before finishing. Nothing was paid; you can hand it over again.";
  if (/ModelSubstituted/.test(t)) return "A reply came from the wrong model, so the run was stopped.";
  if (/timed? ?out/i.test(t)) return "The model took too long to answer. Hand the ticket over again.";
  return t.length > 160 ? t.slice(0, 159) + "…" : t || "Unknown problem.";
}

/** The manager's stamp, read back in plain words. */
export function managerGist(e: AuditEvent): string {
  const r = e.result ?? "";
  const verb = e.tool_name === "reject" ? "VOID" : "APPROVED";
  if (/^refused/.test(r)) return `Register refused: ${r.replace(/^refused:\s*/, "")}`;
  if (r.includes('"paid":true')) {
    const amt = r.match(/"amount":([\d.]+)/)?.[1];
    const eff = pluck(r, "effect");
    return `Stamped ${verb}: paid $${Number(amt).toLocaleString()}${eff ? ` (${eff})` : ""}.`;
  }
  if (r.startsWith("ticket resolved")) return "Ticket FILLED: nothing left for the manager.";
  return `Stamped ${verb}.`;
}

export type LineKind = "pickup" | "think" | "tool" | "pass" | "return" | "done" | "trouble" | "manager";
export interface Line {
  key: string;
  time: string;
  agent: string;
  kind: LineKind;
  text: string;
  detail?: string | null;
  to?: string;
}

/** Turn one audit event into one line of counter talk (or null if it adds nothing). */
export function toLine(e: AuditEvent, i: number): Line | null {
  const s = staffOf(e.agent);
  const base = { key: `${e.time}-${i}`, time: e.time, agent: e.agent };
  switch (e.step_type) {
    case "run_start":
      return { ...base, kind: "pickup", text: s ? `${s.greet}` : "Picked up a slip.", detail: e.args };
    case "model_reply": {
      if (e.stop_reason === "final_output") return { ...base, kind: "think", text: "Writing it up for the slip." };
      if (e.stop_reason === "length") return { ...base, kind: "trouble", text: "Lost the thread (reply ran out of room)." };
      const tools = (e.args ?? "").split(",").map((t) => t.trim()).filter((t) => t && t !== "ask_agent");
      if (!tools.length) return null;
      return { ...base, kind: "think", text: `Reaching for: ${tools.map(toolVerb).join("; ").toLowerCase()}.` };
    }
    case "tool_call":
      if (e.tool_name === "ask_agent") return null; // shown as a passed slip instead
      return { ...base, kind: "tool", text: toolVerb(e.tool_name), detail: resultGist(e) };
    case "delegation": {
      const m = (e.tool_name ?? "").match(/ask_agent ([-<>]+) (\w+)/);
      if (!m) return null;
      const other = m[2];
      if (m[1] === "->") return { ...base, kind: "pass", to: other, text: `Passes a slip to ${staffOf(other)?.name ?? other}`, detail: e.args };
      return { ...base, kind: "return", to: other, text: `${staffOf(other)?.name ?? other} slid it back`, detail: pluck(e.result, "answer") ?? pluck(e.result, "message") };
    }
    case "run_end": {
      const answer = pluck(e.result, "answer") ?? pluck(e.result, "summary");
      return { ...base, kind: "done", text: s?.signoff ?? "Done.", detail: answer };
    }
    case "limit_stop":
      return { ...base, kind: "trouble", text: "Had to stop here: hit a limit.", detail: e.stop_reason };
    case "error":
      return { ...base, kind: "trouble", text: "Something went wrong.", detail: friendlyError(e.stop_reason) };
    case "human_decision":
      return { ...base, agent: "manager", kind: "manager", text: managerGist(e), detail: e.args };
    default:
      return null;
  }
}

export type StationState = "idle" | "working" | "waiting" | "done" | "trouble";
export interface StationView {
  state: StationState;
  waitingOn?: string;
  last?: Line;
  toolCount: number;
  tools: string[];
  passedTo: string[];
  answer?: string | null;
}

/** Work out what every station is doing from the ticket's events. */
export function stations(events: AuditEvent[]): Record<AgentKey, StationView> {
  const out = Object.fromEntries(
    AGENT_KEYS.map((k) => [k, { state: "idle", toolCount: 0, tools: [], passedTo: [] } as StationView]),
  ) as Record<AgentKey, StationView>;
  const open: Record<string, number> = {};
  const waiting: Record<string, string[]> = {};
  events.forEach((e, i) => {
    const v = (out as Record<string, StationView>)[e.agent];
    if (!v) return;
    const line = toLine(e, i);
    if (line) v.last = line;
    if (e.step_type === "run_start") { open[e.agent] = (open[e.agent] ?? 0) + 1; v.state = "working"; }
    if (e.step_type === "run_end") {
      open[e.agent] = Math.max(0, (open[e.agent] ?? 1) - 1);
      v.state = open[e.agent] ? "working" : "done";
      v.answer = pluck(e.result, "answer") ?? pluck(e.result, "summary");
    }
    if (e.step_type === "limit_stop" || e.step_type === "error") v.state = "trouble";
    if (e.step_type === "tool_call" && e.tool_name && e.tool_name !== "ask_agent") {
      v.toolCount += 1;
      if (!v.tools.includes(e.tool_name)) v.tools.push(e.tool_name);
    }
    if (e.step_type === "delegation") {
      const m = (e.tool_name ?? "").match(/ask_agent ([-<>]+) (\w+)/);
      if (m && m[1] === "->") {
        if (!v.passedTo.includes(m[2])) v.passedTo.push(m[2]);
        (waiting[e.agent] ??= []).push(m[2]);
        v.state = "waiting"; v.waitingOn = m[2];
      } else if (m) {
        waiting[e.agent] = (waiting[e.agent] ?? []).filter((x) => x !== m[2]);
        v.waitingOn = waiting[e.agent].at(-1);
        if (!v.waitingOn && open[e.agent]) v.state = "working";
      }
    }
  });
  return out;
}

export function money(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export const ITEM_LABEL: Record<string, string> = {
  payment: "Payment",
  purchase_order: "Purchase order",
  price_override: "Price override",
  customer_message: "Customer draft",
};
