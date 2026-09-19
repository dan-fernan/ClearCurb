import type { Barrier, BarrierKind, LonLat, RouteFeature, RouteFeatureCollection, RouteResponse } from "./types";

// The backend reports each segment's penalties as free text (backend/app/profiles.py evaluate_edge):
//   sidewalk: "grade 6.2%", "2 open violation(s)", "trip hazard", "broken pavement", "undermined",
//             "sloped defect", "missing sidewalk"
//   crossing: "no verified ramp", "ramp slope 9.1%", "cross slope 3.0%", "curb lip 1.0 in", "raised crosswalk"
//   step:     "step street"
// A segment this profile cannot use at all is described as "blocked: <reason>", e.g. "blocked: ramp missing",
// "blocked: grade 12.1%". Only the standard route can contain those; the accessible route avoids them.
// These functions map that text onto the design's barrier types.

const SIDEWALK_DEFECTS = [
  "open violation",
  "trip hazard",
  "broken pavement",
  "undermined",
  "sloped defect",
  "missing sidewalk",
];

/** Step streets have no measured grade; give them a value that reads as the steepest class. */
const STEP_GRADE_PCT = 12;

const EDGE_LABEL = {
  sidewalk: "Sidewalk",
  crossing: "Crossing",
  step: "Step street",
  link: "Connector",
} as const;

const SOURCE: Record<BarrierKind, string> = {
  missing_ramp: "Pedestrian ramp survey",
  ramp_issue: "Pedestrian ramp survey",
  bad_sidewalk: "DOT sidewalk violations",
  grade: "LiDAR DEM",
};

const BLOCKED = "blocked: ";
const stripBlocked = (w: string) => (w.startsWith(BLOCKED) ? w.slice(BLOCKED.length) : w);

function classify(warning: string): BarrierKind | null {
  const w = stripBlocked(warning);
  if (w.startsWith("no verified ramp") || w.startsWith("ramp missing") || w.startsWith("ramp found at one end")) {
    return "missing_ramp";
  }
  if (/^(ramp slope|cross slope|curb lip)/.test(w)) return "ramp_issue";
  if (w.startsWith("grade") || w === "step street") return "grade";
  if (SIDEWALK_DEFECTS.some((k) => w.includes(k))) return "bad_sidewalk";
  return null; // "raised crosswalk" and the like are informational, not barriers
}

/** Grade in percent for a segment's warnings, or null if none apply. */
export function gradeFromWarnings(warnings: string[]): number | null {
  for (const raw of warnings) {
    const w = stripBlocked(raw);
    if (w === "step street") return STEP_GRADE_PCT;
    const m = /^grade (\d+(?:\.\d+)?)%/.exec(w);
    if (m) return parseFloat(m[1]);
  }
  return null;
}

function midpoint(f: RouteFeature): LonLat {
  const c = f.geometry.coordinates;
  return c[Math.floor(c.length / 2)];
}

/** One barrier per (segment, type), in route order. ``prefix`` keeps ids unique across routes. */
export function deriveBarriers(fc: RouteFeatureCollection, prefix: string): Barrier[] {
  const out: Barrier[] = [];
  fc.features.forEach((f, i) => {
    const { edge_id, edge_type, length_ft, warnings } = f.properties;
    const byKind = new Map<BarrierKind, string[]>();
    for (const w of warnings) {
      const kind = classify(w);
      if (kind) byKind.set(kind, [...(byKind.get(kind) ?? []), w]);
    }
    for (const [kind, notes] of byKind) {
      const grade = kind === "grade" ? gradeFromWarnings(notes) : null;
      const isStep = notes.some((n) => stripBlocked(n) === "step street");
      const title =
        kind === "missing_ramp"
          ? "No verified curb ramp"
          : kind === "ramp_issue"
            ? "Curb ramp issue"
            : kind === "bad_sidewalk"
              ? "Sidewalk defects"
              : isStep
                ? "Step street"
                : `${grade?.toFixed(1)}% grade`;
      out.push({
        id: `${prefix}-${i}-${kind}`,
        edgeId: edge_id,
        blocked: notes.some((n) => n.startsWith(BLOCKED)),
        kind,
        title,
        detail: notes.join(", "),
        source: `${EDGE_LABEL[edge_type]} · ${Math.round(length_ft)} ft · ${SOURCE[kind]}`,
        lonlat: midpoint(f),
        ...(grade !== null ? { gradePct: grade } : {}),
      });
    }
  });
  return out;
}

export interface Metrics {
  minutes: number;
  miles: number;
  crossings: number;
  maxGradePct: number;
  missingCurbCuts: number;
  poorSidewalk: number;
}

export interface Comparison {
  accessible: Metrics;
  /** null only if the backend could not produce a standard route. */
  standard: Metrics | null;
  extraMinutes: number | null;
  percentLonger: number | null;
  /** The accessible route is the same set of segments as the standard route. */
  identical: boolean;
  /** Barriers only on the standard route that this profile cannot use at all. */
  avoidedBlocked: number;
}

export interface Analysis {
  /** Barriers along the accessible route. */
  accessible: Barrier[];
  /** Barriers on the standard route that the accessible route does not pass: what it avoids. */
  avoided: Barrier[];
  comparison: Comparison;
}

function metrics(summary: RouteResponse["summary"], barriers: Barrier[]): Metrics {
  return {
    minutes: summary.estimated_minutes,
    miles: summary.length_miles,
    crossings: summary.crossings,
    maxGradePct: summary.max_grade_pct,
    missingCurbCuts: barriers.filter((b) => b.kind === "missing_ramp").length,
    poorSidewalk: barriers.filter((b) => b.kind === "bad_sidewalk").length,
  };
}

export function analyze(r: RouteResponse): Analysis {
  const accessible = deriveBarriers(r.route, "a");
  const accessibleMetrics = metrics(r.summary, accessible);

  if (!r.standard) {
    return {
      accessible,
      avoided: [],
      comparison: {
        accessible: accessibleMetrics,
        standard: null,
        extraMinutes: null,
        percentLonger: null,
        identical: false,
        avoidedBlocked: 0,
      },
    };
  }

  const standardBarriers = deriveBarriers(r.standard.route, "s");
  const standardMetrics = metrics(r.standard.summary, standardBarriers);

  const onAccessible = new Set(r.route.features.map((f) => f.properties.edge_id));
  const avoided = standardBarriers.filter((b) => !onAccessible.has(b.edgeId));
  const onStandard = r.standard.route.features.map((f) => f.properties.edge_id);
  const identical =
    onStandard.length === onAccessible.size && onStandard.every((id) => onAccessible.has(id)) && avoided.length === 0;

  const extra = accessibleMetrics.minutes - standardMetrics.minutes;
  const d = r.summary.detour_vs_shortest;
  return {
    accessible,
    avoided,
    comparison: {
      accessible: accessibleMetrics,
      standard: standardMetrics,
      extraMinutes: extra,
      percentLonger: d && d > 1 ? Math.round((d - 1) * 100) : 0,
      identical,
      avoidedBlocked: avoided.filter((b) => b.blocked).length,
    },
  };
}
