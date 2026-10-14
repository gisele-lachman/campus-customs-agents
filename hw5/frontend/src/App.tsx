import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type AuditEvent, type Cash, type PendingItem, type Run, type Ticket } from "./api";
import { API_BASE } from "./config";
import { Badge, BellIcon, Crest, InkFilters, RollingNumber, Stamp, useBell, useElapsed } from "./art";
import {
  AGENT_KEYS, ITEM_LABEL, STAFF, friendlyError, money, pluck, staffOf, stations, toLine,
  type AgentKey, type Line, type StationView,
} from "./staff";

const FAST_POLL = 1500;
const SLOW_POLL = 5000;
const OFFLINE_AFTER_FAILURES = 3;
const TICKET_KIND: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Price override",
};

type Notice = { tone: "ok" | "refused" | "error"; text: string; id: number };

export default function App() {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [cash, setCash] = useState<Cash | null>(null);
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [offline, setOffline] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [registerSays, setRegisterSays] = useState<string | null>(null);
  const [busyItem, setBusyItem] = useState<number | null>(null);
  const [freshStamp, setFreshStamp] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [soundOn, setSoundOn] = useState(false);
  const [manager, setManager] = useState("Ms. Lachman");
  const bell = useBell(soundOn);
  const prevRunStatus = useRef<Record<number, string>>({});
  const selectedRef = useRef<number | null>(null);
  selectedRef.current = selected;
  const activeRef = useRef<number | null>(null);
  activeRef.current = activeRunId;
  const failures = useRef(0);

  const say = (tone: Notice["tone"], text: string) => setNotice({ tone, text, id: Date.now() });

  const refresh = useCallback(async () => {
    try {
      const [t, c, p, r] = await Promise.all([api.tickets(), api.cash(), api.pending(), api.runs()]);
      setTickets(t);
      setCash(c);
      setPending(p);
      setRuns(r.runs);
      setActiveRunId(r.active_run_id);
      failures.current = 0;
      setOffline(null);
      // A run that just finished rings the bell.
      for (const run of r.runs) {
        const before = prevRunStatus.current[run.id];
        if (before === "running" && run.status !== "running") {
          if (run.status === "finished") { bell(); say("ok", `Order up! Ticket ${run.ticket_id} is back from the counter.`); }
          else say("error", `Ticket ${run.ticket_id}'s run stopped early. ${friendlyError(run.error)}`);
        }
        prevRunStatus.current[run.id] = run.status;
      }
      const sel = selectedRef.current;
      if (sel !== null) {
        const ev = await api.events(sel);
        if (selectedRef.current === sel) setEvents(ev.events);
      }
    } catch (e) {
      // Only speak up after several misses in a row (about 15 s), so one slow poll doesn't flash a warning.
      failures.current += 1;
      if (failures.current >= OFFLINE_AFTER_FAILURES) setOffline(e instanceof ApiError ? e.message : String(e));
    }
  }, [bell]);

  // Exactly one polling loop for the life of the page: fast while a run is going, slow otherwise.
  useEffect(() => {
    let stop = false;
    let timer: number;
    const tick = async () => {
      await refresh();
      if (!stop) timer = window.setTimeout(tick, activeRef.current !== null ? FAST_POLL : SLOW_POLL);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [refresh]);

  // Picking a different ticket loads its order pad right away (no second loop).
  useEffect(() => {
    if (selected !== null) refresh();
  }, [selected, refresh]);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 7000);
    return () => clearTimeout(t);
  }, [notice]);

  const activeRun = runs.find((r) => r.id === activeRunId) ?? null;
  const selectedTicket = tickets?.find((t) => t.id === selected) ?? null;
  const selectedRun = useMemo(
    () => [...runs].reverse().find((r) => r.ticket_id === selected) ?? null,
    [runs, selected],
  );
  const lines = useMemo(() => events.map(toLine).filter((l): l is Line => l !== null), [events]);
  const views = useMemo(() => stations(events), [events]);

  async function startRun(id: number) {
    setSelected(id);
    setEvents([]);
    setStarting(true);
    try {
      await api.run(id);
      bell();
      say("ok", `Ticket ${id} handed over the counter. Watch the staff work it.`);
      await refresh();
    } catch (e) {
      say("error", e instanceof ApiError ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }

  async function decide(item: PendingItem, approve: boolean) {
    setBusyItem(item.id);
    setRegisterSays(null);
    try {
      const r = approve ? await api.approve(item.id, manager) : await api.reject(item.id, manager);
      setFreshStamp(item.id);
      if (approve && item.item_type === "payment") { bell(); }
      say("ok", `${ITEM_LABEL[item.item_type]} #${item.id} stamped ${approve ? (r.status === "paid" ? "APPROVED and paid" : "APPROVED") : "VOID"}.` +
        (r.ticket_resolved ? ` Ticket ${item.ticket_id} is FILLED.` : ""));
      await refresh();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      if (approve && item.item_type === "payment") setRegisterSays(msg);
      else say("refused", msg);
    } finally {
      setBusyItem(null);
    }
  }

  async function doReset() {
    setResetting(true);
    try {
      await api.reset();
      setConfirmReset(false);
      setEvents([]);
      setSelected(null);
      setRegisterSays(null);
      prevRunStatus.current = {};
      say("ok", "New shift started. Fresh slips on the rail, the till is back to its opening count.");
      await refresh();
    } catch (e) {
      say("error", e instanceof ApiError ? e.message : String(e));
    } finally {
      setResetting(false);
    }
  }

  const nowServing = activeRun?.ticket_id ?? selected;

  return (
    <div className="shop">
      <InkFilters />
      <header className="awning">
        <div className="awning-stripes" aria-hidden="true" />
        <div className="sign">
          <Crest />
          <div>
            <h1>The Ticket Counter</h1>
            <p className="sign-sub">Campus Customs · Hand over a ticket, the staff work it, the manager stamps it</p>
          </div>
        </div>
        <div className="header-tools">
          <div className="now-serving" aria-live="polite">
            <span className="ns-label">Now serving</span>
            <span className="ns-number">{nowServing ?? "--"}</span>
          </div>
          <label className="manager-name">
            <span>Store manager</span>
            <input value={manager} maxLength={40} onChange={(e) => setManager(e.target.value)} />
          </label>
          <button className={`icon-btn ${soundOn ? "on" : ""}`} onClick={() => setSoundOn((s) => !s)}
                  aria-pressed={soundOn} title={soundOn ? "Bell on: click to mute" : "Bell muted: click to turn on"}>
            <BellIcon on={soundOn} /> <span>{soundOn ? "Bell on" : "Bell off"}</span>
          </button>
          <button className="btn btn-shift" onClick={() => setConfirmReset(true)} disabled={activeRunId !== null}
                  title={activeRunId !== null ? "Can't start a new shift while an order is being worked" : "Restore the shop to the start of the day"}>
            Start a new shift
          </button>
        </div>
      </header>

      <div className="toasts" aria-live="polite">
        {offline && (
          <div className="banner banner-error" role="alert">
            <strong>Back office isn't answering.</strong> {offline} Still retrying quietly in the background.
          </div>
        )}
        {notice && (
          <div className={`banner banner-${notice.tone}`} role="status" key={notice.id}>
            {notice.text}
            <button className="banner-x" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
          </div>
        )}
      </div>

      <main className="floor">
        <TicketRail tickets={tickets} selected={selected} activeTicket={activeRun?.ticket_id ?? null}
                    runs={runs} starting={starting} onSelect={(id) => { setSelected(id); setEvents([]); }}
                    onRun={startRun} runBusy={activeRunId !== null} />

        <section className="counter" aria-label="Behind the counter">
          <RunBar ticket={selectedTicket} run={selectedRun} active={activeRun?.ticket_id === selected} />
          <div className="stations">
            {AGENT_KEYS.map((k) => <Station key={k} agent={k} view={views[k]} />)}
          </div>
          <div className="lower">
            <PassThrough events={events} />
            <OrderPad lines={lines} ticket={selected} running={activeRun?.ticket_id === selected} />
          </div>
          {selectedRun?.status === "finished" && selectedRun.decision && (
            <OrderUp run={selectedRun} views={views} resolved={selectedTicket?.status === "resolved"} />
          )}
        </section>

        <aside className="till" aria-label="Register and manager's desk">
          <Register cash={cash} pending={pending} registerSays={registerSays} onClear={() => setRegisterSays(null)} />
          <ManagerDesk items={pending} busy={busyItem} fresh={freshStamp} onDecide={decide} focusTicket={selected} />
        </aside>
      </main>

      <footer className="floor-foot">
        Backend: <code>{API_BASE}</code> · Every slip is a draft until a manager stamps it · No emails, no vendor calls
      </footer>

      {confirmReset && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-labelledby="shift-title">
          <div className="modal slip">
            <h2 id="shift-title">Start a new shift?</h2>
            <p>This puts the shop back to the start of the day:</p>
            <ul>
              <li>The working database is restored from the original (the original is only read).</li>
              <li>All slips, pending items, runs and ticket statuses are cleared.</li>
              <li>The audit trail is <b>kept</b>; a "new shift" marker hides older events from this screen.</li>
            </ul>
            <div className="modal-actions">
              <button className="btn" onClick={() => setConfirmReset(false)} autoFocus>Keep working</button>
              <button className="btn btn-danger" onClick={doReset} disabled={resetting}>
                {resetting ? "Restocking…" : "Yes, start a new shift"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ ticket rail */

function TicketRail(props: {
  tickets: Ticket[] | null; selected: number | null; activeTicket: number | null; runs: Run[];
  starting: boolean; runBusy: boolean; onSelect: (id: number) => void; onRun: (id: number) => void;
}) {
  const { tickets, selected, activeTicket, runs, starting, runBusy, onSelect, onRun } = props;
  return (
    <section className="rail" aria-label="Order rail">
      <h2 className="section-title">The order rail</h2>
      <div className="rail-wire" aria-hidden="true" />
      {tickets === null && <p className="empty">Opening the shop…</p>}
      {tickets?.length === 0 && <p className="empty">No tickets on the rail.</p>}
      {tickets?.map((t, i) => {
        const last = [...runs].reverse().find((r) => r.ticket_id === t.id);
        const working = activeTicket === t.id;
        const finished = last?.status === "finished";
        const failed = last?.status === "failed";
        const canRun = t.status === "open" && !finished && !runBusy && !starting;
        return (
          <article key={t.id} className={`slip ticket ${selected === t.id ? "is-selected" : ""} ${t.status}`}
                   style={{ ["--tilt" as string]: `${[-1.2, 0.8, -0.5][i % 3]}deg` }}
                   onClick={() => onSelect(t.id)} tabIndex={0}
                   onKeyDown={(e) => { if (e.key === "Enter") onSelect(t.id); }}
                   aria-label={`Ticket ${t.id}, ${t.subject}, ${t.status}`}>
            <span className="clip" aria-hidden="true" />
            <div className="ticket-top">
              <span className="ticket-no">No. {t.id}</span>
              <span className="ticket-kind">{TICKET_KIND[t.type] ?? t.type}</span>
            </div>
            <div className="ticket-subject">{t.subject}</div>
            <div className="ticket-from">for <b>{t.requester}</b></div>
            <div className="ticket-status">
              {working && <span className="chip chip-live">On the grill…</span>}
              {!working && t.status === "open" && !last && <span className="chip">Waiting on the rail</span>}
              {!working && t.status === "open" && finished && <span className="chip chip-gold">{t.waiting_on_human} slip{t.waiting_on_human === 1 ? "" : "s"} for the manager</span>}
              {!working && failed && <span className="chip chip-bad">Run stopped early, can retry</span>}
              {t.status === "resolved" && <span className="chip chip-ok">Resolved</span>}
            </div>
            {t.status === "open" && (
              <button className="btn btn-hand" disabled={!canRun}
                      onClick={(e) => { e.stopPropagation(); onRun(t.id); }}
                      title={finished ? "Already worked; waiting on the manager's stamps" : runBusy ? "One order at a time" : "Start the agent team on this ticket"}>
                {working ? "Being worked…" : finished ? "Waiting on manager" : starting && selected === t.id ? "Handing over…" : "Hand it over the counter"}
              </button>
            )}
            {t.status === "resolved" && <div className="ticket-stamp"><Stamp text="FILLED" tone="red" /></div>}
          </article>
        );
      })}
    </section>
  );
}

/* ------------------------------------------------------------------ the counter */

function RunBar({ ticket, run, active }: { ticket: Ticket | null; run: Run | null; active: boolean }) {
  const elapsed = useElapsed(active ? run?.started_at : null);
  if (!ticket) {
    return <div className="runbar slip-plain"><b>The counter's quiet.</b> Pick a ticket off the rail to see who works it.</div>;
  }
  const secs = (() => { const [m, s] = elapsed.split(":").map(Number); return m * 60 + s; })();
  return (
    <div className="runbar slip-plain">
      <span className="runbar-title">Ticket No. {ticket.id}: {ticket.subject}</span>
      {active && (
        <span className="runbar-live">
          <span className="pulse" aria-hidden="true" /> Working it · {elapsed}
          {secs > 45 && secs <= 240 && <em> · Big order, still going. Limits keep it from running forever.</em>}
          {secs > 240 && <em> · Taking unusually long; it will stop at its limits if stuck.</em>}
        </span>
      )}
      {!active && run?.status === "finished" && <span className="runbar-done">Worked · decision on the slip below</span>}
      {!active && run?.status === "failed" && <span className="runbar-bad" title={run.error ?? ""}>Stopped early. {friendlyError(run.error)}</span>}
      {!active && !run && <span className="runbar-idle">Not handed over yet</span>}
    </div>
  );
}

const STATE_LABEL: Record<StationView["state"], string> = {
  idle: "At the station",
  working: "Working",
  waiting: "Waiting on",
  done: "Done",
  trouble: "Trouble",
};

function Station({ agent, view }: { agent: AgentKey; view: StationView }) {
  const s = STAFF[agent];
  return (
    <article className={`station state-${view.state}`} style={{ ["--staff" as string]: s.color, ["--staff-ink" as string]: s.ink }}>
      <div className="station-head">
        <Badge agent={agent} />
        <div className="nametag">
          <span className="nametag-hello">Hello, my name is</span>
          <span className="nametag-name">{s.name}</span>
        </div>
      </div>
      <div className="station-role">{s.role} · <span>{s.station}</span></div>
      <div className={`station-state st-${view.state}`}>
        {STATE_LABEL[view.state]}{view.state === "waiting" && view.waitingOn ? ` ${staffOf(view.waitingOn)?.name ?? view.waitingOn}` : ""}
        {view.state === "working" && <span className="dots" aria-hidden="true"><i /><i /><i /></span>}
      </div>
      <div className="speech" aria-live="polite">
        {view.last ? (
          <>
            <p className="speech-text">{view.last.text}</p>
            {view.last.detail && <p className="speech-detail">{view.last.detail}</p>}
          </>
        ) : (
          <p className="speech-text quiet">Wiping down the counter.</p>
        )}
      </div>
      {view.toolCount > 0 && <div className="station-tally">{view.toolCount} tool call{view.toolCount === 1 ? "" : "s"}</div>}
    </article>
  );
}

function PassThrough({ events }: { events: AuditEvent[] }) {
  const passes = events
    .map((e, i) => ({ e, i, m: (e.tool_name ?? "").match(/ask_agent ([-<>]+) (\w+)/) }))
    .filter((x) => x.e.step_type === "delegation" && x.m);
  return (
    <section className="pass" aria-label="Pass-through window">
      <h2 className="section-title">Pass-through window</h2>
      {passes.length === 0 && <p className="empty">No slips passed yet. When one station hands work to another, it shows up here.</p>}
      <ol className="pass-list">
        {passes.map(({ e, i, m }) => {
          const out = m![1] === "->";
          const from = out ? e.agent : m![2];
          const to = out ? m![2] : e.agent;
          const fs = staffOf(from), ts = staffOf(to);
          const text = out ? e.args : pluck(e.result, "answer") ?? pluck(e.result, "message");
          return (
            <li key={i} className={`pass-slip ${out ? "out" : "back"}`} style={{ marginLeft: `${Math.min(e.depth, 3) * 18}px` }}>
              <span className="who" style={{ background: fs?.color }}>{fs?.name ?? from}</span>
              <span className="arrow" aria-hidden="true">{out ? "──slip──▶" : "◀──back──"}</span>
              <span className="who" style={{ background: ts?.color }}>{ts?.name ?? to}</span>
              {text && <p className="pass-text" title={text}>{out ? "“" : ""}{text}{out ? "”" : ""}</p>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function OrderPad({ lines, ticket, running }: { lines: Line[]; ticket: number | null; running: boolean }) {
  const end = useRef<HTMLLIElement | null>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [lines.length]);
  return (
    <section className="pad" aria-label="Order pad: everything said, newest last">
      <h2 className="section-title">Order pad <small>(newest last)</small></h2>
      {ticket === null && <p className="empty">Pick a ticket to read its order pad.</p>}
      {ticket !== null && lines.length === 0 && (
        <p className="empty">{running ? "Slip's on the counter. First words coming…" : "Nothing written on this one yet."}</p>
      )}
      <ol className="pad-lines">
        {lines.map((l, i) => {
          const s = staffOf(l.agent);
          return (
            <li key={l.key} className={`pad-line k-${l.kind}`} ref={i === lines.length - 1 ? end : undefined}>
              <span className="pad-time">{new Date(l.time).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
              <span className="pad-who" style={{ color: s?.ink ?? "#5b4636" }}>{s?.name ?? "MANAGER"}</span>
              <span className="pad-text">
                {l.text}
                {l.detail && <span className="pad-detail"> {l.detail}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

const DECISION_LABEL: Record<string, string> = {
  proceed_pending_approval: "Go ahead, pending the manager",
  blocked: "Blocked",
  decline: "Declined",
  needs_more_info: "Needs more info",
};

function OrderUp({ run, views, resolved }: { run: Run; views: Record<AgentKey, StationView>; resolved: boolean }) {
  const d = run.decision!;
  const worked = AGENT_KEYS.filter((k) => views[k].state !== "idle");
  const idle = AGENT_KEYS.filter((k) => views[k].state === "idle");
  return (
    <section className="orderup slip" aria-label="Order up summary">
      <div className="orderup-head">
        <h2>Order up! Ticket No. {d.ticket_id}</h2>
        {resolved ? <Stamp text="ORDER UP" tone="green" /> : <Stamp text="AWAITING STAMP" tone="navy" small />}
      </div>
      <p className="orderup-decision"><b>Sal's call:</b> {DECISION_LABEL[d.decision] ?? d.decision}</p>
      <p>{d.summary}</p>
      <h3>Who did what</h3>
      <ul className="orderup-staff">
        {worked.map((k) => {
          const v = views[k], s = STAFF[k];
          return (
            <li key={k}>
              <span className="who" style={{ background: s.color }}>{s.name}</span>{" "}
              {v.tools.length ? <>used {v.tools.join(", ")}</> : <>no tools</>}
              {v.passedTo.length > 0 && <> · passed slips to {v.passedTo.map((p) => staffOf(p)?.name ?? p).join(", ")}</>}
              {v.answer && <span className="orderup-answer"> “{v.answer}”</span>}
            </li>
          );
        })}
      </ul>
      {idle.length > 0 && <p className="note">Stayed at their stations: {idle.map((k) => STAFF[k].name).join(", ")}.</p>}
      {d.human_actions_needed.length > 0 && (
        <>
          <h3>For the manager</h3>
          <ul>{d.human_actions_needed.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ register + manager's desk */

function Register({ cash, pending, registerSays, onClear }: { cash: Cash | null; pending: PendingItem[]; registerSays: string | null; onClear: () => void }) {
  const paid = pending.filter((p) => p.status === "paid");
  const out = paid.reduce((sum, p) => sum + (p.amount ?? 0), 0);
  return (
    <section className="register" aria-label="Cash register">
      <div className="register-body">
        <div className="register-crown" aria-hidden="true"><span>CHECKING</span></div>
        <div className={`register-window ${registerSays ? "refused" : ""}`}>
          {cash ? <RollingNumber value={cash.balance} /> : <span className="register-loading">- - - -</span>}
        </div>
        <div className="register-keys" aria-hidden="true">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((k) => <span key={k}>{k}</span>)}
        </div>
        <div className="register-drawer" aria-hidden="true" />
      </div>
      {registerSays && (
        <div className="register-refusal" role="alert">
          <div className="refusal-head">*** NO SALE ***</div>
          <p>The register won't ring this one up.</p>
          <p className="refusal-msg">{registerSays}</p>
          <button className="btn btn-small" onClick={onClear}>OK</button>
        </div>
      )}
      <div className="tape" aria-label="Receipt tape">
        <div className="tape-head">CAMPUS CUSTOMS · CHECKING<br />{cash?.date ?? ""}</div>
        <div className="tape-row"><span>OPENING</span><span>{cash ? money(cash.balance + out) : "—"}</span></div>
        {paid.length === 0 && <div className="tape-row muted"><span>no payments yet</span><span /></div>}
        {paid.map((p) => (
          <div key={p.id} className="tape-row">
            <span>{p.pay_kind === "rent" ? `RENT LEASE ${p.ref_id}` : `INV ${p.ref_id}`}<br /><small>ok'd by {p.decided_by}</small></span>
            <span>-{money(p.amount)}</span>
          </div>
        ))}
        <div className="tape-row total"><span>BALANCE</span><span>{cash ? money(cash.balance) : "—"}</span></div>
        <div className="tape-tear" aria-hidden="true" />
      </div>
    </section>
  );
}

function ManagerDesk({ items, busy, fresh, focusTicket, onDecide }: {
  items: PendingItem[]; busy: number | null; fresh: number | null; focusTicket: number | null;
  onDecide: (i: PendingItem, approve: boolean) => void;
}) {
  const sorted = [...items].sort((a, b) => {
    const wa = a.status === "pending" ? 0 : 1, wb = b.status === "pending" ? 0 : 1;
    const fa = a.ticket_id === focusTicket ? 0 : 1, fb = b.ticket_id === focusTicket ? 0 : 1;
    return wa - wb || fa - fb || a.id - b.id;
  });
  const waiting = items.filter((i) => i.status === "pending").length;
  return (
    <section className="desk" aria-label="Manager's desk">
      <h2 className="section-title">Manager's desk <small>({waiting} waiting)</small></h2>
      {items.length === 0 && <p className="empty">Nothing on the spike. Slips the staff write up land here for your stamp.</p>}
      {sorted.map((it) => {
        const s = staffOf(it.prepared_by);
        const decided = it.status !== "pending";
        const stamp = it.status === "paid" ? "PAID" : it.status === "approved" ? "APPROVED" : it.status === "rejected" ? "VOID" : null;
        return (
          <article key={it.id} className={`slip item ${decided ? "decided" : ""}`}>
            <div className="item-top">
              <span className="item-kind">{ITEM_LABEL[it.item_type]} #{it.id}</span>
              <span className="item-ticket">Ticket {it.ticket_id}</span>
            </div>
            <div className="item-main">
              {it.item_type === "payment" && <><b>{money(it.amount)}</b> {it.pay_kind === "rent" ? `rent, lease ${it.ref_id}` : `invoice ${it.ref_id}`}</>}
              {it.item_type === "purchase_order" && <><b>{it.qty} × {it.sku} {it.size}</b> from vendor {it.vendor_id} · {money(it.amount)}</>}
              {it.item_type === "price_override" && <><b>{it.qty} × {it.sku}</b> at {money(it.unit_amount)} each · {money(it.amount)}</>}
              {it.item_type === "customer_message" && <><b>To {it.recipient}:</b> {it.subject}</>}
            </div>
            {it.item_type === "customer_message" && it.body && <p className="item-body">{it.body}</p>}
            {it.reason && <p className="item-reason">Why: {it.reason}</p>}
            <p className="item-by">Written up by <span style={{ color: s?.ink }}>{s?.name ?? it.prepared_by}</span>
              {decided && it.decided_by ? <> · stamped by {it.decided_by}</> : null}</p>
            {it.status === "approved" && it.item_type === "payment" && <p className="item-warn">Approved but not paid yet (register refused). Stamp again when there's cash, or VOID it.</p>}
            {stamp && <div className="item-stamp"><Stamp text={stamp} tone={stamp === "VOID" ? "red" : "green"} fresh={fresh === it.id} small /></div>}
            {(!decided || (it.status === "approved" && it.item_type === "payment")) && (
              <div className="item-actions">
                <button className="btn btn-approve" disabled={busy !== null} onClick={() => onDecide(it, true)}>
                  {busy === it.id ? "Stamping…" : it.item_type === "payment" ? "APPROVE & pay" : "APPROVE"}
                </button>
                <button className="btn btn-void" disabled={busy !== null} onClick={() => onDecide(it, false)}>VOID</button>
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
}
