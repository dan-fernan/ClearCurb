import { ImageResponse } from "next/og";

// Modernist tokens from modernist.css, inlined because image rendering has no access to CSS variables.
const ACCENT = "#ec3013";
const GROUND = "#f3f2f2";

/** ClearCurb mark: a squared "C" (a curb's corner) cut out of the accent square. */
export function brandIcon(px: number) {
  const u = px / 32; // the mark is drawn on a 32-unit grid
  const box = (x: number, y: number, w: number, h: number, color: string) => (
    <div style={{ position: "absolute", left: x * u, top: y * u, width: w * u, height: h * u, background: color }} />
  );

  return new ImageResponse(
    (
      <div style={{ display: "flex", position: "relative", width: px, height: px, background: ACCENT }}>
        {box(6, 6, 20, 20, GROUND)}
        {box(11, 11, 15, 10, ACCENT)}
      </div>
    ),
    { width: px, height: px },
  );
}
