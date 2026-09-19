# Handoff: ClearCurb — accessibility-aware walking route planner (NYC)

## Overview
ClearCurb plans walking routes for wheelchair and mobility-device users in NYC. Unlike a general
map app, it computes **two routes for every trip** — a standard pedestrian route and an
accessible route — and shows exactly which physical barriers the accessible route avoids, using
NYC open data (curb ramp inventory, sidewalk condition / 311, LiDAR-derived grade) plus user
hazard reports.

Two products are documented here:
- **Desktop web app (primary, current focus)** — 1440 × 900, two states: `2a` plan & compare,
  `2b` report a hazard.
- **Mobile screens (earlier exploration, keep for reference)** — four 390 × 844 screens,
  including a data-confidence screen that is **deprioritized** for now.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended
look and behavior, not production code to copy. `ClearCurb.dc.html` is a streaming
"Design Component" file: markup plus a small logic class, rendered by `support.js`. Treat it as a
visual spec.

The task is to **recreate these designs in the target codebase's own environment** (React, Vue,
Svelte, native, etc.) using its established patterns, router, state library, and map SDK. If no
environment exists yet, choose an appropriate stack — a React + MapLibre GL / Mapbox GL app is the
natural fit, since every screen is a real slippy map with vector overlays.

The maps in the prototype are **schematic SVG stand-ins for a real map canvas**. Do not port the
SVG. Port the *encoding*: route line styles, barrier marker styles, hatching for unknown data.

## Fidelity
**High-fidelity.** Colors, type, spacing, and copy are final. Layout proportions (rail widths,
band heights, type sizes) should be matched closely. The one exception is the map itself, which is
a placeholder for a real tile/vector map.

Everything is built on the **Modernist** design system (bundled: `_ds/modernist-.../styles.css`
and `readme.md`). Its rules are binding: zero border radius anywhere, 2px rules between major
sections, Archivo throughout, flush-left labels including inside buttons, one accent red.

---

## Screens / Views

### 2a — Plan & compare (desktop, 1440 × 900)
**Purpose:** enter origin/destination, set a mobility profile and strictness, and compare the
standard vs. accessible route. The comparison is the core "aha" and must be the most prominent
element on the screen.

**Layout**
- Outer frame: 2px solid `#201e1d` border, background `#f3f2f2`, `display:flex; flex-direction:column`.
- **Top bar** (`flex:none`, bottom border 2px solid text):
  - Brand cell: `padding: 0 20px`, right border 2px solid text. Wordmark `CLEARCURB` — Archivo 800, 20px, `letter-spacing:-0.02em`. Next to it a `NYC` chip: 10px/800, `letter-spacing:.08em`, `padding:2px 6px`, background text, color bg.
  - FROM field: `flex:1`, `padding:12px 16px`, right border 1px divider. 10px square outline marker (2px solid text) + `FROM` label (10px/800, .08em, 60% text) + value (14px/600). Value: "Union Square, E 14 St & Broadway".
  - TO field: same, marker is a 10px solid accent square. Value: "Bellevue Hospital, 1 Av & E 27 St".
  - `REPORT A HAZARD` button: accent fill, bg-colored text, Archivo 800 14px, `padding: 0 22px`, Lucide `triangle-alert` 16px leading icon. Hover `#dd2b0f`.
- **Body** (`flex:1`, row):
  - **Left rail, 360px fixed**, right border 2px solid text, column:
    1. Controls block (`padding:18px 20px`, bottom border 2px divider):
       - `MOBILITY PROFILE` label (10px/800, .1em), then a 3-cell segmented control in a 1px text
         border, `grid-template-columns: 1fr 1fr 1fr`. Options: `MANUAL CHAIR` / `POWER CHAIR` /
         `WALKER`. Cell: `padding:10px 6px`, Archivo 800 11px, `.04em`, **text-align:left**.
         Selected = background `#201e1d`, color `#f3f2f2`. Unselected = bg ground, ink text.
       - `ROUTING STRICTNESS` label with a right-aligned live note (10px, 55% text) that changes
         with the selection: hard → "Never route over a barrier", soft → "Detour only if cheap".
       - 2-cell segmented control, same styling: `SOFT PENALTIES` / `HARD CONSTRAINTS`.
       - Constraint summary row (11px, 60% text, gap 14px): "Max grade 5.0%", "Min width 36 in",
         "Curb ramp required". These should be derived from the active profile.
    2. `THE ACCESSIBLE ROUTE AVOIDS` list (bottom border 2px divider). Each row: 12px marker +
       title (14px/600) + source line (11px, 55% text). Markers encode barrier type:
       - missing curb ramp → 12px circle, filled `#ae1800`
       - bad sidewalk → 12px square, 3px `#dd2b0f` border, bg fill
       - grade → 12px square filled with `linear-gradient(90deg, #ffe0d9, #ae1800)`
       Rows in the mock: "No curb ramp — E 18 St & 3 Av / SE corner · DOT survey, Mar 2026";
       "No curb ramp — E 23 St & 2 Av / NW corner · DOT survey, Mar 2026";
       "Broken sidewalk — 3 Av, E 19–20 St / 311 complaints ×4 · 2 user reports";
       "9.0% grade — E 20 St bridge approach / LiDAR DEM · 1 ft resolution".
    3. Bottom (`margin-top:auto`): a small `DATA CONFIDENCE` meter — label + `38% UNINSPECTED`
       (11px/800, `#ae1800`), a 14px bar with 1px text border split 57% accent / 38% hatch /
       5% ink, and an 11px note: "Hatched segments have no inspection record. They are unverified,
       not cleared." *(This is the only surviving piece of the deprioritized confidence feature;
       it can be dropped without affecting anything else.)*
  - **Map column** (`flex:1`, column):
    - Map canvas `flex:1`. Overlays:
      - top-left: context chip "MANHATTAN · GRAMERCY — KIPS BAY" (bg, 1px text border, 10px/800)
        and a state chip "BARRIER OVERLAY ON" (ink fill, bg text).
      - top-right: zoom stack, two 38px cells in a single 1px text border, `+` / `−` 19px/800.
      - bottom-left: legend card (bg, 1px text border, `padding:11px 13px`, 2-column grid,
        `gap:8px 22px`), entries: STANDARD ROUTE (26px dashed 5px ink line), ACCESSIBLE ROUTE
        (26×6 accent bar), MISSING CURB RAMP (12px `#ae1800` dot), BAD SIDEWALK (12px square,
        3px `#dd2b0f` border), GRADE SEVERITY (26×6 accent-200→accent-700 gradient),
        NO INSPECTION DATA (26×6 45° hatch, `#7d7979` on `#f8f4f4`).
    - **Comparison band** (`flex:none`, top border 2px solid text,
      `grid-template-columns: 1fr 1fr 210px`) — the visual anchor of the screen:
      - **Standard cell** (`padding:18px 22px 20px`, right border 2px text): 28px dashed rule +
        `STANDARD ROUTE` (11px/800, .1em); headline `18 min` — Archivo 800 **56px** with the unit
        at 20px; sub "0.9 mi · 14 crossings" (12px, 58% text); 2px divider; a 3-column metric grid:
        MISSING CURB CUTS `3`, MAX GRADE `9.0%`, POOR SIDEWALK `2` — labels 10px/800 at 60% text,
        values Archivo 800 30px in `#ae1800`.
      - **Accessible cell**: identical structure, **full accent `#ec3013` field** with `#f3f2f2`
        type. Headline `24 min`; sub "1.1 mi · 16 crossings · **+6 min**"; metrics `0`, `4.2%`, `0`.
      - **Trade-off cell** (210px, left border 2px text): label `TRADE-OFF`, copy "Six minutes
        longer, three fewer barriers you cannot cross.", then a full-width `START ACCESSIBLE`
        button (accent fill, top border 2px text, 16px padding, left-aligned Archivo 800 14px).

**Map encoding (both desktop states)**
| Meaning | Style |
| --- | --- |
| Standard route | `#201e1d`, 6px, dashed `14 9` |
| Accessible route | `#ec3013`, 8px, solid |
| Grade severity overlay | 16px line, gradient `#ffe0d9 → #ae1800`, 50% opacity, drawn under markers |
| Missing curb ramp | 9px circle, fill `#ae1800`, 3px `#f3f2f2` halo stroke |
| Bad sidewalk | 16px square, fill bg, 4px `#dd2b0f` stroke |
| No inspection data | route line stroked with a 45° hatch pattern (8px tile, 4px `#7d7979` stripe on `#f8f4f4`) |
| Origin | 9px circle, no fill, 4px ink stroke |
| Destination | 18px solid accent square |
| Street grid (placeholder) | ground `#d7d3d3`, avenues 12px `#f8f4f4`, cross streets 6px, block fills `#bab6b6` |

### 2b — Report a hazard (desktop, 1440 × 900)
**Purpose:** file a hazard in seconds, and see what has already been reported nearby.

- **Top bar**: brand cell unchanged; middle shows `REPORT MODE` label + "Click the map to place
  the hazard — Esc to cancel"; right `CANCEL` button (ground fill, 2px left border, hover
  `#eae7e7`).
- **Left rail (360px)**:
  1. "Report a hazard" (Archivo 800 22px) + "Three steps, about ten seconds." Then three numbered
     steps: 22px square badges — step 1 ink fill, step 2 accent fill, step 3 2px ink outline —
     with 14px copy: "Click the map to drop a pin, or drag an existing one." / "Pick a category.
     A note and photo are optional." / "Submit. Routing picks it up on the next request."
  2. `REPORTS NEARBY` + "Last 30 days". Three rows (title Archivo 800 14px, meta 11px 55%, status
     chip right-aligned):
     - "Broken sidewalk · 3 Av, E 19–20 St" / "2 reports · 4 days ago" / `ACTIVE` (accent fill)
     - "Construction · E 23 St & 2 Av" / "1 report · 11 days ago" / `UNVERIFIED` (1px divider outline)
     - "Obstruction · E 18 St, scaffold" / "Cleared by DOT · 19 days ago" / `RESOLVED` (outline, 55% text)
  3. Bottom: `27` (Archivo 800 34px) + "reports you have filed. 19 of them now change how routes
     are drawn."
- **Map**: the active route in accent, existing report markers (filled `#ae1800` dot = confirmed,
  3px `#dd2b0f` outlined square = unverified), and the **drop target**: concentric accent circles
  at 14% and 26% opacity (r 54 / r 30) under a 20px accent square pin with a 3px bg stroke.
  Legend bottom-left: YOUR ROUTE / EXISTING REPORT / UNVERIFIED REPORT.
- **Report popover**: absolutely positioned `right:28px; top:28px`, width 420px, bg fill, 2px text
  border, `box-shadow: 0 12px 32px rgba(45,43,43,.22)`.
  - Header (bottom border 2px text): `REPORTING AT` label; "E 14 St & 3 Av" Archivo 800 24px with
    " · SE corner" in accent; "40.7331, −73.9865 · drag the pin to adjust" (11px, 55%).
  - Category grid: `grid-template-columns: 1fr 1fr`, `gap:2px` on an ink background so the gaps
    read as rules. Five tiles + a sixth `SELECTED` readout cell. Tile: column layout, flush left,
    `padding:12px`, `min-height:76px`, 20px Lucide-style icon above an Archivo 800 12px label.
    Selected tile = accent fill / bg text; unselected = bg / ink.
    Categories: BROKEN SIDEWALK, MISSING RAMP, STEEP INCLINE, OBSTRUCTION, CONSTRUCTION.
  - Note row: `NOTE` label, placeholder "Optional — one line" (14px, 45% text), `+ PHOTO` action
    (11px/800, `#ae1800`), bottom 1px divider.
  - `SUBMIT REPORT` — full-width accent button, Archivo 800 16px, left-aligned, with `⏎ ENTER`
    right-aligned at 11px/600.
  - Footer note (11px, 58%): "Live for other users immediately; flagged unverified until a second
    report or a DOT inspection confirms it."

### Mobile screens (reference only, 390 × 844)
Screens 01 map & controls, 02 route comparison, 03 report a hazard, 04 data confidence. Same
tokens and encodings. Screen 02 stacks the comparison as two vertical cells (ink | accent) under a
300px map. Screen 04 (data confidence: 38% uninspected, per-source provenance table, hatched
legend) is **currently out of scope** — keep it only as reference if the confidence feature is
revived.

---

## Interactions & Behavior
- **Profile selector** (3 options) and **strictness** (2 options) are single-select segmented
  controls; changing either re-runs routing. Strictness changes the note text and, semantically:
  *soft* = barriers add a cost penalty and may still be routed over; *hard* = barriers are
  impassable edges and the router fails loudly rather than silently routing over one.
- **Profile presets** drive the constraint summary (max grade, min width, curb ramp required) —
  manual chair and power chair differ in grade tolerance, walker in width/ramp needs.
- **Comparison band**: hovering a metric should highlight the corresponding features on the map;
  clicking a row in "the accessible route avoids" should pan/zoom to that barrier.
- **Report flow**: entering report mode puts the map in click-to-place; the pin is draggable; the
  popover anchors to the pin; category selection is one click; Enter submits. Submission is
  optimistic — show the new marker immediately as unverified.
- **Report status lifecycle**: unverified → active (second report or DOT confirmation) → resolved.
- **Hover states** come from the accent ramp: accent `#ec3013` → hover `#dd2b0f` → active `#ae1800`.
  Ground buttons hover to `#eae7e7`.
- **Focus**: `:focus-visible { outline: 2px solid #ec3013; outline-offset: 2px }`. Never the
  browser default — this product's users include keyboard and switch-device users.
- **Accessibility requirements beyond visuals**: every route metric must be available as text to a
  screen reader (the comparison should read as a table, not as decorative numbers); color is never
  the only channel — route type is also dash vs solid, barrier type is also shape (circle vs
  square vs hatch); minimum body text 12px, metric labels 10px uppercase at 800 weight for legibility.
- No animation is specified. If added, keep it under 150ms and respect `prefers-reduced-motion`.

## State Management
- `origin`, `destination` (geocoded points; also settable by map click)
- `profile`: `'manual' | 'power' | 'walker'`
- `strictness`: `'soft' | 'hard'`
- `routes`: `{ standard, accessible }`, each `{ durationMin, distanceMi, crossings, missingCurbCuts, maxGradePct, poorSidewalkSegments, geometry, barriers[] }`
- `selectedRoute`: which route is started
- `barriers[]`: `{ id, type: 'missing_ramp' | 'bad_sidewalk' | 'grade' | 'obstruction' | 'construction', location, source, confidence }`
- `reportMode`: boolean; `reportDraft`: `{ latLng, category, note, photo }`
- `nearbyReports[]`: `{ id, category, location, count, ageDays, status }`
- Data fetching: routing endpoint returns both routes in one call (they must be computed against
  the same graph snapshot); barrier overlay tiles load per viewport; nearby reports load per
  viewport with a 30-day window.

## Design Tokens
From `_ds/modernist-186b7d62-2ffb-4b4e-a0ad-0101b1b58c25/styles.css` — use the CSS variables, not
raw hex, wherever the target codebase allows.

**Color**
- `--color-bg` `#f3f2f2` · `--color-surface` `#eae9e9` · `--color-text` `#201e1d`
- `--color-accent` `#ec3013` · `--color-divider` `rgba(32,30,29,.4)`
- Neutral ramp: 100 `#f8f4f4`, 200 `#eae7e7`, 300 `#d7d3d3`, 400 `#bab6b6`, 500 `#9b9797`,
  600 `#7d7979`, 700 `#605d5d`, 800 `#444141`, 900 `#2d2b2b`
- Accent ramp: 100 `#fff2ef`, 200 `#ffe0d9`, 300 `#ffc4b8`, 400 `#ff9783`, 500 `#ff563c`,
  600 `#dd2b0f`, 700 `#ae1800`, 800 `#7c1405`, 900 `#4d170e`
- Accent text on the light ground must be `#ae1800` (accent-700) at body size; `#ec3013` is only
  cleared for large type, fills, and chrome.

**Type** — Archivo (400 / 600 / 800) for both headings and body.
Scale used: 56 / 44 / 34 / 30 / 24 / 22 / 20 / 16 / 15 / 14 / 13 / 12 / 11 / 10px.
Headings: weight 800, `line-height:1.1`, `letter-spacing:-0.015em`. Body 15px/1.55.
Uppercase micro-labels: 10–11px, weight 800, `letter-spacing:.06–.1em`.

**Spacing** — 4 / 8 / 12 / 16 / 24 / 32px.
**Radius** — `0` everywhere. Do not round anything.
**Shadow** — sm `0 1px 2px rgba(45,43,43,.14)`, md `0 3px 10px rgba(45,43,43,.16)`,
lg `0 12px 32px rgba(45,43,43,.22)` (used only on the report popover).
**Rules** — 2px `--color-divider` between major sections; 1px for list rows.

## Assets
- **Icons**: Lucide (https://lucide.dev). The prototype hand-draws simplified equivalents; in code
  use the real Lucide set — `triangle-alert` (construction/report), `construction`, `move-up-right`
  or `trending-up` (incline), `square-x` (obstruction), `waves`/`route` (broken sidewalk),
  `accessibility` (profile), `plus`/`minus` (zoom), `chevron-left`, `arrow-right`.
- **Map**: no asset shipped. Use a vector basemap (MapLibre/Mapbox) styled to the neutral ramp:
  ground `#d7d3d3`, street casings `#f8f4f4`, no color in the basemap at all — the accent is
  reserved for route and hazard data.
- **Fonts**: Archivo via Google Fonts (`@import` already in `styles.css`), weights 400/600/800.
- **Data sources referenced in copy**: NYC DOT curb ramp survey, 311 sidewalk complaints, LiDAR
  DEM (1 ft), and ClearCurb user reports.

## Files
- `ClearCurb.dc.html` — all screens: desktop `2a` and `2b` first, then the four mobile reference
  screens. Open in a browser to view; `support.js` must sit alongside it.
- `support.js` — runtime that renders the design-component file (not part of the deliverable app).
- `_ds/modernist-186b7d62-2ffb-4b4e-a0ad-0101b1b58c25/styles.css` — the design system's tokens and
  component classes. **This is the authoritative source for every value above.**
- `_ds/modernist-186b7d62-2ffb-4b4e-a0ad-0101b1b58c25/readme.md` — the design system's written
  rules (grid, flush-left labels, accent discipline, no radius).
- `_ds/modernist-186b7d62-2ffb-4b4e-a0ad-0101b1b58c25/_ds_bundle.js` — component bundle used by
  the prototype.
