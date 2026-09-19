// Hazard reports. There is no reports endpoint on the backend yet, so these live in memory only.

export type ReportCategory =
  | "broken_sidewalk"
  | "missing_ramp"
  | "steep_incline"
  | "obstruction"
  | "construction";

export const REPORT_CATEGORIES: { value: ReportCategory; label: string }[] = [
  { value: "broken_sidewalk", label: "BROKEN SIDEWALK" },
  { value: "missing_ramp", label: "MISSING RAMP" },
  { value: "steep_incline", label: "STEEP INCLINE" },
  { value: "obstruction", label: "OBSTRUCTION" },
  { value: "construction", label: "CONSTRUCTION" },
];

export function categoryLabel(c: ReportCategory): string {
  return REPORT_CATEGORIES.find((x) => x.value === c)?.label ?? c;
}

export interface ReportDraft {
  lat: number;
  lon: number;
  category: ReportCategory | null;
  note: string;
}

export interface Report {
  id: string;
  category: ReportCategory;
  lat: number;
  lon: number;
  note: string;
  /** Wall-clock time it was filed, formatted when submitted. */
  filedAt: string;
  status: "unverified";
}
