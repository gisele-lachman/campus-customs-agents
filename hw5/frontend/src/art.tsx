// Every graphic in the dashboard is drawn here by hand (inline SVG / CSS); no image files.
import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentKey } from "./staff";

/** Shared SVG filters: a rough ink edge for rubber stamps. Rendered once. */
export function InkFilters() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <filter id="ink-rough">
        <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3" result="noise" />
        <feDisplacementMap in="SourceGraphic" in2="noise" scale="2.2" xChannelSelector="R" yChannelSelector="G" result="d" />
        <feComponentTransfer in="d">
          <feFuncA type="discrete" tableValues="0 1 1 1 1 0.85 1 1" />
        </feComponentTransfer>
      </filter>
    </svg>
  );
}

/** One badge per station, so you can tell the staff apart without reading. */
export function Badge({ agent, size = 44 }: { agent: AgentKey; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 48 48", "aria-hidden": true } as const;
  switch (agent) {
    case "boss": // the order spike
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="22" fill="#1f3a5f" />
          <circle cx="24" cy="24" r="19" fill="none" stroke="#c9a54a" strokeWidth="1.5" strokeDasharray="2 2" />
          <rect x="22.8" y="9" width="2.4" height="26" fill="#c0c4c9" />
          <path d="M16 20h16l-2 4H18z" fill="#f3ead7" />
          <path d="M15 26h18l-2 4H17z" fill="#efe1c4" />
          <ellipse cx="24" cy="37" rx="10" ry="3" fill="#c9a54a" />
        </svg>
      );
    case "inventory": // a stock crate
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="22" fill="#3f6b4e" />
          <rect x="12" y="15" width="24" height="19" rx="1.5" fill="#d9b77a" stroke="#6b4e1e" strokeWidth="1.5" />
          <path d="M12 21h24M12 28h24M16 15v19M32 15v19" stroke="#8a6a32" strokeWidth="1.3" />
          <path d="M14 34l20-19" stroke="#8a6a32" strokeWidth="1.3" />
        </svg>
      );
    case "accounting": // ledger + coin
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="22" fill="#722f37" />
          <rect x="11" y="13" width="20" height="23" rx="1.5" fill="#f3ead7" stroke="#3b1a1e" strokeWidth="1.3" />
          <path d="M15 19h12M15 23h12M15 27h8" stroke="#722f37" strokeWidth="1.3" />
          <circle cx="32" cy="31" r="7" fill="#c9a54a" stroke="#7a5a12" strokeWidth="1.3" />
          <text x="32" y="34.5" textAnchor="middle" fontSize="9" fontWeight="700" fill="#5a3f0a" fontFamily="Courier Prime, monospace">$</text>
        </svg>
      );
    case "facilities": // a big building key
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="22" fill="#7a5a12" />
          <circle cx="17" cy="24" r="6.5" fill="none" stroke="#e9d9a8" strokeWidth="3" />
          <path d="M23 24h14M33 24v5M37 24v4" stroke="#e9d9a8" strokeWidth="3" strokeLinecap="round" />
        </svg>
      );
    case "customer_service": // the counter phone
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="22" fill="#4a5568" />
          <path d="M14 18c0-3 3-5 10-5s10 2 10 5l-3 2-3-2v-2h-8v2l-3 2z" fill="#d7dbe0" />
          <rect x="15" y="22" width="18" height="12" rx="3" fill="#c0c4c9" />
          <circle cx="24" cy="28" r="3.2" fill="#4a5568" />
        </svg>
      );
  }
}

/** A rubber stamp. `fresh` plays the thunk animation once. */
export function Stamp({ text, tone, fresh = false, small = false }: { text: string; tone: "red" | "green" | "navy"; fresh?: boolean; small?: boolean }) {
  return (
    <span className={`stamp stamp-${tone} ${fresh ? "stamp-fresh" : ""} ${small ? "stamp-small" : ""}`} aria-label={text}>
      <span className="stamp-ink">{text}</span>
    </span>
  );
}

/** Odometer-style digits: each digit is a strip of 0-9 that rolls to its place. */
export function RollingNumber({ value }: { value: number }) {
  const text = value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return (
    <span className="rolling" aria-label={`$${text}`} role="img">
      <span className="rolling-char rolling-sign">$</span>
      {text.split("").map((ch, i) =>
        /\d/.test(ch) ? (
          <span className="rolling-digit" key={`${text.length}-${i}`}>
            <span className="rolling-strip" style={{ transform: `translateY(-${Number(ch) * 10}%)` }}>
              {"0123456789".split("").map((d) => <span key={d}>{d}</span>)}
            </span>
          </span>
        ) : (
          <span className="rolling-char" key={`${text.length}-${i}`}>{ch}</span>
        ),
      )}
    </span>
  );
}

/** Counter bell, synthesized with Web Audio (no sound files). Silent unless enabled. */
export function useBell(enabled: boolean) {
  const ctx = useRef<AudioContext | null>(null);
  const on = useRef(enabled);
  on.current = enabled;
  // Stable function: a new one every render would restart anything that depends on it (like polling).
  return useCallback(() => {
    if (!on.current) return;
    try {
      ctx.current ??= new AudioContext();
      const ac = ctx.current;
      const now = ac.currentTime;
      [1760, 2637, 3520].forEach((f, i) => {
        const o = ac.createOscillator();
        const g = ac.createGain();
        o.type = "sine";
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, now);
        g.gain.exponentialRampToValueAtTime(0.18 / (i + 1), now + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, now + 1.4);
        o.connect(g).connect(ac.destination);
        o.start(now);
        o.stop(now + 1.5);
      });
    } catch {
      /* audio unavailable: stay quiet */
    }
  }, []);
}

export function BellIcon({ on }: { on: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M6 17a6 6 0 0 1 12 0z" fill="currentColor" />
      <rect x="11" y="7" width="2" height="4" rx="1" fill="currentColor" />
      <circle cx="12" cy="6.5" r="1.6" fill="currentColor" />
      {!on && <path d="M4 4l16 16" stroke="#8b1e2b" strokeWidth="2.2" strokeLinecap="round" />}
    </svg>
  );
}

/** Live elapsed time since a timestamp, in m:ss. */
export function useElapsed(since: string | null | undefined): string {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!since) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [since]);
  if (!since) return "0:00";
  const s = Math.max(0, Math.floor((now - Date.parse(since)) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The counter's crest: a sandwich in a gold-rimmed navy seal. */
export function Crest() {
  return (
    <svg width="58" height="58" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="30" fill="#1f3a5f" stroke="#c9a54a" strokeWidth="3" />
      <circle cx="32" cy="32" r="24" fill="none" stroke="#c9a54a" strokeWidth="1" strokeDasharray="3 3" />
      <path d="M17 36c2-8 28-8 30 0z" fill="#d9b77a" />
      <path d="M16 37h32" stroke="#3f6b4e" strokeWidth="3" strokeLinecap="round" />
      <path d="M17 40h30" stroke="#a6463f" strokeWidth="3" strokeLinecap="round" />
      <path d="M18 43c2 4 26 4 28 0z" fill="#d9b77a" />
      <text x="32" y="27" textAnchor="middle" fontSize="8" fill="#f3ead7" fontFamily="Special Elite, monospace">EST. 1701</text>
    </svg>
  );
}
