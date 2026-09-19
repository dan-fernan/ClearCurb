// Shapes returned by the FastAPI backend (backend/app/main.py, routing.py).

export type LonLat = [number, number];

export interface Health {
  status: string;
  graph_loaded: boolean;
}

export interface ApiProfile {
  key: string;
  label: string;
}

export type EdgeType = "sidewalk" | "crossing" | "step" | "link";

export interface RouteFeature {
  type: "Feature";
  geometry: { type: "LineString"; coordinates: LonLat[] };
  properties: {
    /** Index of the graph edge, stable within one response: lets us tell which segments two routes share. */
    edge_id: number;
    edge_type: EdgeType;
    length_ft: number;
    /** Plain-English notes from profiles.evaluate_edge, e.g. "grade 6.2%", "no verified ramp". */
    warnings: string[];
  };
}

export interface RouteFeatureCollection {
  type: "FeatureCollection";
  features: RouteFeature[];
}

export interface RouteSummary {
  profile: string;
  length_ft: number;
  length_miles: number;
  estimated_minutes: number;
  crossings: number;
  max_grade_pct: number;
  total_ascent_ft: number;
  uses_unverified_crossings: boolean;
  warning_counts: Record<string, number>;
  /** Route length / plain shortest-path length over the same graph. null when unavailable. */
  detour_vs_shortest: number | null;
}

export interface SnappedPoint {
  lonlat: LonLat;
  snap_distance_ft: number;
}

/** The plain shortest path over the same graph, ignoring accessibility, described like the accessible route. */
export interface StandardRoute {
  route: RouteFeatureCollection;
  summary: RouteSummary;
}

export interface RouteResponse {
  route: RouteFeatureCollection;
  summary: RouteSummary;
  snapped: { start: SnappedPoint; end: SnappedPoint };
  /** null only if the two points are not connected at all. */
  standard: StandardRoute | null;
}

// ---- Frontend-only types ----------------------------------------------------------------------

export interface Place {
  lat: number;
  lon: number;
  label: string;
}

export type Strictness = "soft" | "hard";

export type BarrierKind = "missing_ramp" | "ramp_issue" | "bad_sidewalk" | "grade";

/** One flagged stretch of the accessible route, derived from the per-segment warnings. */
export interface Barrier {
  id: string;
  edgeId: number;
  /** True when this profile cannot use the segment at all (only ever the case on the standard route). */
  blocked: boolean;
  kind: BarrierKind;
  title: string;
  detail: string;
  source: string;
  lonlat: LonLat;
  /** Grade in percent, when kind === "grade". Step streets are treated as the steepest class. */
  gradePct?: number;
}
