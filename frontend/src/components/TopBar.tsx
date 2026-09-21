"use client";

import { TriangleAlert } from "lucide-react";
import Link from "next/link";
import type { Place } from "@/lib/types";

export type PickTarget = "origin" | "destination";

interface FieldProps {
  kind: "from" | "to";
  place: Place | null;
  hint: string | null;
  active: boolean;
  onClick: () => void;
}

function Field({ kind, place, hint, active, onClick }: FieldProps) {
  const name = kind === "from" ? "FROM" : "TO";
  return (
    <button
      type="button"
      className="cc-field"
      aria-pressed={active}
      aria-label={`${name}: ${place?.label ?? "not set"}. Activate, then click the map to change it.`}
      onClick={onClick}
    >
      <span className={`cc-field__marker cc-field__marker--${kind}`} aria-hidden />
      <span className="cc-field__text">
        <span className="cc-field__label">{name}</span>
        <span className="cc-field__value">{place?.label ?? "Click to set on the map"}</span>
        {hint && <span className="cc-field__hint">{hint}</span>}
      </span>
    </button>
  );
}

interface Props {
  mode: "plan" | "report";
  origin: Place | null;
  destination: Place | null;
  originHint: string | null;
  destinationHint: string | null;
  pickTarget: PickTarget | null;
  onPick: (t: PickTarget) => void;
  onStartReport: () => void;
  onEndReport: () => void;
  hasDraft: boolean;
}

export default function TopBar(p: Props) {
  return (
    <header className="cc-top">
      <div className="cc-brand">
        <h1 className="cc-wordmark">
          <Link href="/" aria-label="ClearCurb home">
            CLEARCURB
          </Link>
        </h1>
        <span className="cc-chip">NYC</span>
      </div>

      {p.mode === "plan" ? (
        <>
          <Field kind="from" place={p.origin} hint={p.originHint} active={p.pickTarget === "origin"} onClick={() => p.onPick("origin")} />
          <Field kind="to" place={p.destination} hint={p.destinationHint} active={p.pickTarget === "destination"} onClick={() => p.onPick("destination")} />
          <button type="button" className="cc-cta" onClick={p.onStartReport}>
            <TriangleAlert size={16} aria-hidden />
            REPORT A HAZARD
          </button>
        </>
      ) : (
        <>
          <div className="cc-top__mode">
            <span className="cc-label">Report mode</span>
            <p>Click the map to place the hazard — Esc to cancel</p>
          </div>
          <button type="button" className="cc-ground-btn" onClick={p.onEndReport}>
            {p.hasDraft ? "CANCEL" : "DONE"}
          </button>
        </>
      )}
    </header>
  );
}
