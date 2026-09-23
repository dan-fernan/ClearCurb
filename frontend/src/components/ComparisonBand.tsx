"use client";

import { ArrowRight } from "lucide-react";
import type { Comparison } from "@/lib/route-metrics";

export type BandState =
  | { kind: "idle" }
  | { kind: "loading"; stale: Comparison | null }
  | { kind: "error"; message: string; canRelax: boolean }
  | { kind: "ready"; comparison: Comparison };

interface Props {
  state: BandState;
  started: boolean;
  onStart: () => void;
  onRelax: () => void;
}

const fmtMinutes = (m: number) => (m < 1 ? "<1" : String(Math.round(m)));
/** "5 minutes", "1 minute", "under a minute": reads correctly for any positive amount. */
const fmtExtra = (m: number) => (m < 1 ? "under a minute" : `${Math.round(m)} minute${Math.round(m) === 1 ? "" : "s"}`);
const fmtMiles = (m: number) => m.toFixed(m < 0.1 ? 2 : 1);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function describeTradeoff(c: Comparison): string {
  if (!c.standard || c.extraMinutes === null) {
    return "A comparison with the plain shortest path isn't available for this trip.";
  }
  if (c.identical) return "The shortest path is already accessible for this profile. Nothing to avoid.";
  const sameTime = c.extraMinutes < 0.5;
  const cap = (t: string) => t.replace(/^./, (ch) => ch.toUpperCase());
  const n = c.avoidedBlocked;
  if (n > 0) {
    // Same shape as the design: "Six minutes longer, three fewer barriers you cannot cross."
    return `${sameTime ? "About the same time" : `${cap(fmtExtra(c.extraMinutes))} longer`}, ${n} fewer barrier${n === 1 ? "" : "s"} you cannot cross.`;
  }
  return sameTime
    ? "About the same time as the plain shortest path."
    : `${cap(fmtExtra(c.extraMinutes))} longer than the plain shortest path (${c.percentLonger}% more distance).`;
}

function Metric({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="cc-metric__label">{label}</div>
      <div className={`cc-metric__value${value === null ? " cc-metric__value--none" : ""}`}>{value ?? "—"}</div>
    </div>
  );
}

export default function ComparisonBand({ state, started, onStart, onRelax }: Props) {
  if (state.kind === "idle") {
    return (
      <section className="cc-band" aria-label="Route comparison">
        <div className="cc-statuscell">
          <div>
            <h2>Choose a start and end</h2>
            <p>Select FROM or TO above, then click the map to place it.</p>
          </div>
        </div>
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section className="cc-band" aria-label="Route comparison">
        <div className="cc-statuscell cc-statuscell--error" role="alert">
          <div>
            <h2>No accessible route</h2>
            <p>{state.message}</p>
            <p className="cc-hint">Hint: routes are currently only supported in Lower Manhattan, below about 14th St.</p>
          </div>
          {state.canRelax && (
            <button type="button" onClick={onRelax}>
              TRY SOFT PENALTIES
            </button>
          )}
        </div>
      </section>
    );
  }

  const c = state.kind === "ready" ? state.comparison : state.stale;
  if (!c) {
    return (
      <section className="cc-band" aria-label="Route comparison" aria-busy="true">
        <div className="cc-statuscell" role="status">
          <div>
            <h2>Finding the accessible route…</h2>
          </div>
        </div>
      </section>
    );
  }

  const { accessible: a, standard: s } = c;
  const tradeoff = describeTradeoff(c);

  return (
    <section className="cc-band" aria-label="Route comparison" aria-busy={state.kind === "loading"}>
      {/* The same numbers as a real table for screen readers; the visual cells are decorative repeats. */}
      <table className="sr-only">
        <caption>Standard route compared with accessible route</caption>
        <thead>
          <tr>
            <th scope="col">Measure</th>
            <th scope="col">Standard route</th>
            <th scope="col">Accessible route</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Estimated time (minutes)</th>
            <td>{s ? fmtMinutes(s.minutes) : "not available"}</td>
            <td>{fmtMinutes(a.minutes)}</td>
          </tr>
          <tr>
            <th scope="row">Distance (miles)</th>
            <td>{s ? fmtMiles(s.miles) : "not available"}</td>
            <td>{fmtMiles(a.miles)}</td>
          </tr>
          <tr>
            <th scope="row">Crossings</th>
            <td>{s ? s.crossings : "not available"}</td>
            <td>{a.crossings}</td>
          </tr>
          <tr>
            <th scope="row">Missing curb cuts</th>
            <td>{s ? s.missingCurbCuts : "not available"}</td>
            <td>{a.missingCurbCuts}</td>
          </tr>
          <tr>
            <th scope="row">Max grade</th>
            <td>{s ? `${s.maxGradePct.toFixed(1)}%` : "not available"}</td>
            <td>{a.maxGradePct.toFixed(1)}%</td>
          </tr>
          <tr>
            <th scope="row">Poor sidewalk segments</th>
            <td>{s ? s.poorSidewalk : "not available"}</td>
            <td>{a.poorSidewalk}</td>
          </tr>
        </tbody>
      </table>

      <div className="cc-cell cc-cell--standard" aria-hidden>
        <div className="cc-cell__key">
          <span className="cc-linekey cc-linekey--standard" />
          <span className="cc-label">Standard route</span>
        </div>
        <div className="cc-headline">
          {s ? fmtMinutes(s.minutes) : "—"}
          <small>min</small>
        </div>
        <div className="cc-sub">
          {s ? `${fmtMiles(s.miles)} mi · ${plural(s.crossings, "crossing")}` : "Shortest path not available"}
        </div>
        <div className="cc-metrics">
          <Metric label="Missing curb cuts" value={s ? String(s.missingCurbCuts) : null} />
          <Metric label="Max grade" value={s ? `${s.maxGradePct.toFixed(1)}%` : null} />
          <Metric label="Poor sidewalk" value={s ? String(s.poorSidewalk) : null} />
        </div>
      </div>

      <div className="cc-cell cc-cell--accessible" aria-hidden>
        <div className="cc-cell__key">
          <span className="cc-linekey cc-linekey--accessible" />
          <span className="cc-label">Accessible route</span>
        </div>
        <div className="cc-headline">
          {fmtMinutes(a.minutes)}
          <small>min</small>
        </div>
        <div className="cc-sub">
          {fmtMiles(a.miles)} mi · {plural(a.crossings, "crossing")}
          {c.extraMinutes !== null && c.extraMinutes >= 0.5 && <strong> · {c.extraMinutes < 1 ? "<1" : `+${Math.round(c.extraMinutes)}`} min longer</strong>}
        </div>
        <div className="cc-metrics">
          <Metric label="Missing curb cuts" value={String(a.missingCurbCuts)} />
          <Metric label="Max grade" value={`${a.maxGradePct.toFixed(1)}%`} />
          <Metric label="Poor sidewalk" value={String(a.poorSidewalk)} />
        </div>
      </div>

      <div className="cc-tradeoff">
        <div className="cc-tradeoff__body">
          <span className="cc-label">Trade-off</span>
          <p>{tradeoff}</p>
        </div>
        <button type="button" className="cc-start" onClick={onStart} aria-pressed={started}>
          {started ? "ROUTE STARTED" : "START ACCESSIBLE"}
          <ArrowRight size={18} aria-hidden />
        </button>
      </div>
    </section>
  );
}
