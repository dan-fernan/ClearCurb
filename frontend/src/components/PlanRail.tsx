"use client";

import Segmented from "./Segmented";
import type { ApiProfile, Barrier, Strictness } from "@/lib/types";
import { profileLabel, STRICTNESS_OPTIONS } from "@/lib/ui-copy";

export type HealthState =
  | { status: "checking" }
  | { status: "down" }
  | { status: "up"; graphLoaded: boolean };

interface Props {
  health: HealthState;
  profiles: ApiProfile[] | null;
  profilesError: string | null;
  profile: string | null;
  onProfile: (key: string) => void;
  strictness: Strictness;
  onStrictness: (s: Strictness) => void;
  barriers: Barrier[];
  /** Barriers on the standard route that the accessible route does not pass. */
  avoided: Barrier[];
  hasStandard: boolean;
  hasRoute: boolean;
  routeFailed: boolean;
  onFocusBarrier: (b: Barrier) => void;
}

function BarrierList({ barriers, onFocus }: { barriers: Barrier[]; onFocus: (b: Barrier) => void }) {
  return (
    <ul className="cc-list">
      {barriers.map((b) => (
        <li key={b.id}>
          <button
            type="button"
            className="cc-list__row"
            onClick={() => onFocus(b)}
            aria-label={`${b.title}. ${b.detail}. ${b.source}. Show on map.`}
          >
            <span className="cc-list__inner">
              <span className={`cc-mark cc-mark--${b.kind}`} aria-hidden />
              <span>
                <span className="cc-list__title">{b.title}</span>
                <span className="cc-list__meta" style={{ display: "block" }}>
                  {b.detail}
                </span>
                <span className="cc-list__meta" style={{ display: "block" }}>
                  {b.source}
                </span>
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function PlanRail(p: Props) {
  const note = STRICTNESS_OPTIONS.find((o) => o.value === p.strictness)?.note;

  return (
    <aside className="cc-rail" aria-label="Route options">
      {p.health.status === "down" && (
        <div className="cc-banner" role="alert">
          <strong>Backend unreachable.</strong> From <code>backend/</code>, run{" "}
          <code>.venv/bin/uvicorn app.main:app</code>.
        </div>
      )}
      {p.health.status === "up" && !p.health.graphLoaded && (
        <div className="cc-banner" role="alert">
          <strong>Routing graph not built.</strong> Run <code>backend/scripts/attach_attributes.py</code>, then
          restart the backend.
        </div>
      )}

      <div className="cc-block">
        <div className="cc-block__head">
          <span className="cc-label" id="profile-label">
            Mobility profile
          </span>
        </div>
        {p.profiles ? (
          <Segmented
            label="Mobility profile"
            value={p.profile}
            onChange={p.onProfile}
            options={p.profiles.map((x) => ({ value: x.key, label: profileLabel(x) }))}
          />
        ) : (
          <p className="cc-empty" style={{ padding: 0 }} role={p.profilesError ? "alert" : undefined}>
            {p.profilesError ?? "Loading profiles…"}
          </p>
        )}

        <div className="cc-block__head">
          <span className="cc-label">Routing strictness</span>
          <span className="cc-note" aria-live="polite">
            {note}
          </span>
        </div>
        <Segmented
          label="Routing strictness"
          value={p.strictness}
          onChange={p.onStrictness}
          options={STRICTNESS_OPTIONS.map(({ value, label }) => ({ value, label }))}
        />
      </div>

      {p.hasStandard && (
        <div className="cc-block cc-block--flush" style={{ paddingTop: 18 }}>
          <div className="cc-block__head" style={{ padding: "0 20px", margin: "0 0 10px" }}>
            <span className="cc-label">The accessible route avoids</span>
            <span className="cc-note">{p.avoided.length}</span>
          </div>
          {p.avoided.length === 0 ? (
            <p className="cc-empty">Nothing. The shortest path is already accessible for this profile.</p>
          ) : (
            <BarrierList barriers={p.avoided} onFocus={p.onFocusBarrier} />
          )}
        </div>
      )}

      <div className="cc-block cc-block--flush" style={{ paddingTop: 18 }}>
        <div className="cc-block__head" style={{ padding: "0 20px", margin: "0 0 10px" }}>
          <span className="cc-label">Along this route</span>
        </div>
        {!p.hasRoute ? (
          <p className="cc-empty">
            {p.routeFailed ? "There is no route to list. See the message below the map." : "Set a start and end to see what the route passes."}
          </p>
        ) : p.barriers.length === 0 ? (
          <p className="cc-empty">
            No warnings on this route. Missing data is not the same as cleared: segments with no survey or
            violation record show nothing.
          </p>
        ) : (
          <BarrierList barriers={p.barriers} onFocus={p.onFocusBarrier} />
        )}
      </div>
    </aside>
  );
}
