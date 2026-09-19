import type { ApiProfile, Place, Strictness } from "./types";

/** Segmented-control copy from the design. Keys come from GET /api/profiles; unknown keys fall back to the API label. */
const PROFILE_COPY: Record<string, string> = {
  manual: "MANUAL CHAIR",
  power: "POWER CHAIR",
  walker: "WALKER",
};

export function profileLabel(p: ApiProfile): string {
  return PROFILE_COPY[p.key] ?? p.label.toUpperCase();
}

export const STRICTNESS_OPTIONS: { value: Strictness; label: string; note: string }[] = [
  { value: "soft", label: "SOFT PENALTIES", note: "Detour only if cheap" },
  { value: "hard", label: "HARD CONSTRAINTS", note: "Never route over a barrier" },
];

// The graph covers Manhattan south of about 14th St, so the starting points are inside it.
export const DEFAULT_ORIGIN: Place = { lat: 40.7308, lon: -73.9973, label: "Washington Square Park" };
export const DEFAULT_DESTINATION: Place = { lat: 40.7265, lon: -73.9818, label: "Tompkins Square Park" };

export function coordLabel(lat: number, lon: number): string {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}
