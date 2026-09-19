"use client";

import type { KeyboardEvent } from "react";
import { Construction, CircleSlash, CornerDownLeft, Route, SquareX, TrendingUp } from "lucide-react";
import { categoryLabel, REPORT_CATEGORIES, type Report, type ReportCategory, type ReportDraft } from "@/lib/reports";
import { coordLabel } from "@/lib/ui-copy";

const CATEGORY_ICON = {
  broken_sidewalk: Route,
  missing_ramp: CircleSlash,
  steep_incline: TrendingUp,
  obstruction: SquareX,
  construction: Construction,
} satisfies Record<ReportCategory, typeof Route>;

// ---- left rail --------------------------------------------------------------------------------

export function ReportRail({ reports }: { reports: Report[] }) {
  return (
    <aside className="cc-rail" aria-label="Report a hazard">
      <div className="cc-block">
        <h2 className="cc-h-report">Report a hazard</h2>
        <p style={{ margin: 0, fontSize: 14 }}>Three steps, about ten seconds.</p>
        <ol className="cc-steps">
          <li>
            <span className="cc-step cc-step--1" aria-hidden>
              1
            </span>
            <span>Click the map to drop a pin, or drag an existing one.</span>
          </li>
          <li>
            <span className="cc-step cc-step--2" aria-hidden>
              2
            </span>
            <span>Pick a category. A note is optional.</span>
          </li>
          <li>
            <span className="cc-step" aria-hidden>
              3
            </span>
            <span>Submit.</span>
          </li>
        </ol>
      </div>

      <div className="cc-block cc-block--flush" style={{ paddingTop: 18 }}>
        <div className="cc-block__head" style={{ padding: "0 20px", margin: "0 0 10px" }}>
          <span className="cc-label">Reports this session</span>
        </div>
        {reports.length === 0 ? (
          <p className="cc-empty">Nothing filed yet.</p>
        ) : (
          <ul className="cc-list">
            {reports.map((r) => (
              <li key={r.id} className="cc-report-row">
                <div>
                  <div className="cc-report-row__title">{categoryLabel(r.category)}</div>
                  <div className="cc-list__meta">
                    {coordLabel(r.lat, r.lon)} · {r.filedAt}
                  </div>
                  {r.note && <div className="cc-list__meta">{r.note}</div>}
                </div>
                <span className="cc-status">UNVERIFIED</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="cc-bigcount">
        <strong>{reports.length}</strong>
        <span>{reports.length === 1 ? "report" : "reports"} filed this session. Reports are not sent to a server yet.</span>
      </div>
    </aside>
  );
}

// ---- popover ----------------------------------------------------------------------------------

interface PopoverProps {
  draft: ReportDraft;
  onCategory: (c: ReportCategory) => void;
  onNote: (note: string) => void;
  onSubmit: () => void;
}

export function ReportPopover({ draft, onCategory, onNote, onSubmit }: PopoverProps) {
  const canSubmit = draft.category !== null;

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    // Enter submits from the note field; buttons keep Enter for their own activation.
    if (e.key === "Enter" && canSubmit && !(e.target instanceof HTMLButtonElement)) {
      e.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="cc-popover" role="dialog" aria-label="Report a hazard at the pin" onKeyDown={onKeyDown}>
      <div className="cc-popover__head">
        <span className="cc-label">Reporting at</span>
        <h2>{coordLabel(draft.lat, draft.lon)}</h2>
        <p>Drag the pin to adjust</p>
      </div>

      <div className="cc-cats" role="radiogroup" aria-label="Hazard category">
        {REPORT_CATEGORIES.map((c) => {
          const Icon = CATEGORY_ICON[c.value];
          return (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={draft.category === c.value}
              className="cc-cat"
              onClick={() => onCategory(c.value)}
            >
              <Icon size={20} aria-hidden />
              {c.label}
            </button>
          );
        })}
        <div className="cc-cat__selected" aria-live="polite">
          SELECTED
          <span>{draft.category ? categoryLabel(draft.category) : "None yet"}</span>
        </div>
      </div>

      <label className="cc-noterow">
        <span className="cc-label">Note</span>
        <input
          type="text"
          value={draft.note}
          maxLength={140}
          placeholder="Optional — one line"
          onChange={(e) => onNote(e.target.value)}
        />
      </label>

      <button type="button" className="cc-submit" disabled={!canSubmit} onClick={onSubmit}>
        SUBMIT REPORT
        <small>
          <CornerDownLeft size={11} aria-hidden style={{ verticalAlign: "-1px" }} /> ENTER
        </small>
      </button>

      <p className="cc-popover__foot">
        Marked unverified. There is no reports service yet, so this stays in this browser tab and does not
        change routing.
      </p>
    </div>
  );
}
