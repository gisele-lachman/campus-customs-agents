import { API_BASE } from "./config";

export type TicketStatus = "open" | "resolved";
export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  status: TicketStatus;
  last_run: { id: number; status: RunStatus; started_at: string; finished_at: string | null } | null;
  waiting_on_human: number;
}
export type RunStatus = "running" | "finished" | "failed";
export interface Fact { statement: string; source_tool: string }
export interface Decision {
  ticket_id: number;
  decision: "proceed_pending_approval" | "blocked" | "decline" | "needs_more_info";
  summary: string;
  facts: Fact[];
  prepared_item_ids: number[];
  human_actions_needed: string[];
  agents_consulted: string[];
}
export interface Run {
  id: number;
  ticket_id: number;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  decision: Decision | null;
  error: string | null;
  ticket_status?: TicketStatus;
}
export interface AuditEvent {
  time: string;
  ticket: string;
  agent: string;
  step_type: string;
  tool_name: string | null;
  args: string | null;
  result: string | null;
  stop_reason: string | null;
  model: string | null;
  depth: number;
}
export interface PendingItem {
  id: number;
  ticket_id: number | null;
  item_type: "payment" | "purchase_order" | "customer_message" | "price_override";
  status: "pending" | "approved" | "rejected" | "paid" | "refused";
  pay_kind: "invoice" | "rent" | null;
  ref_id: number | null;
  vendor_id: number | null;
  sku: string | null;
  size: string | null;
  qty: number | null;
  unit_amount: number | null;
  amount: number | null;
  recipient: string | null;
  subject: string | null;
  body: string | null;
  reason: string | null;
  prepared_by: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  result_note: string | null;
}
export interface Cash { name: string; balance: number; date: string }

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, `Can't reach the back office at ${API_BASE}. Is the backend running?`);
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export const api = {
  tickets: () => call<Ticket[]>("/api/tickets"),
  run: (id: number) => call<{ run_id: number; ticket_id: number }>(`/api/tickets/${id}/run`, { method: "POST" }),
  runStatus: (runId: number) => call<Run>(`/api/runs/${runId}`),
  runs: () => call<{ active_run_id: number | null; runs: Run[] }>("/api/runs"),
  events: (ticket?: number) =>
    call<{ total: number; events: AuditEvent[] }>(`/api/events?limit=600${ticket ? `&ticket=${ticket}` : ""}`),
  pending: () => call<PendingItem[]>("/api/pending"),
  approve: (id: number, by: string) =>
    call<{ status: string; ticket_resolved: boolean }>(`/api/pending/${id}/approve`, { method: "POST", body: JSON.stringify({ by }) }),
  reject: (id: number, by: string) =>
    call<{ status: string; ticket_resolved: boolean }>(`/api/pending/${id}/reject`, { method: "POST", body: JSON.stringify({ by }) }),
  cash: () => call<Cash>("/api/cash"),
  reset: () => call<{ ok: boolean }>("/api/reset", { method: "POST" }),
};
