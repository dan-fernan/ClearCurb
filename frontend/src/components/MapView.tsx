"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  LngLatBounds,
  Map as MapLibreMap,
  Marker,
  setWorkerUrl,
  type ExpressionSpecification,
  type GeoJSONSource,
} from "maplibre-gl";
import { Minus, Plus } from "lucide-react";
import { BASEMAP_STYLE_URL, FALLBACK_STYLE, HOME_CENTER, HOME_ZOOM } from "@/lib/basemap";
import { gradeFromWarnings } from "@/lib/route-metrics";
import type { Barrier, LonLat, RouteResponse } from "@/lib/types";
import type { Report } from "@/lib/reports";

export interface MapPrompt {
  text: string;
  onCancel: () => void;
}

interface Props {
  mode: "plan" | "report";
  route: RouteResponse | null;
  barriers: Barrier[];
  origin: LonLat | null;
  destination: LonLat | null;
  overlayOn: boolean;
  onToggleOverlay: () => void;
  /** Draw the standard (shortest-path) route from route.standard. */
  standardOn: boolean;
  onToggleStandard: () => void;
  /** Click-to-place is active (picking FROM/TO, or placing a hazard). */
  placing: boolean;
  prompt: MapPrompt | null;
  onPlace: (lat: number, lon: number) => void;
  draft: { lat: number; lon: number } | null;
  onDraftMove: (lat: number, lon: number) => void;
  reports: Report[];
  focus: { lonlat: LonLat; nonce: number } | null;
  children?: ReactNode;
}

// Where the copy step (scripts/copy-maplibre-worker.mjs) puts the worker. MapLibre's default location breaks under bundlers.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const EMPTY = { type: "FeatureCollection" as const, features: [] };

function tokens() {
  const s = getComputedStyle(document.documentElement);
  const t = (n: string) => s.getPropertyValue(n).trim();
  return {
    bg: t("--color-bg"),
    ink: t("--color-text"),
    accent: t("--color-accent"),
    a200: t("--color-accent-200"),
    a600: t("--color-accent-600"),
    a700: t("--color-accent-700"),
  };
}

/** A filled square, optionally outlined, drawn at 2x for crisp edges. Used as a map symbol. */
function squareImage(px: number, fill: string, stroke?: { color: string; width: number }): ImageData {
  const ratio = 2;
  const size = px * ratio;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, size, size);
  if (stroke) {
    const w = stroke.width * ratio;
    ctx.strokeStyle = stroke.color;
    ctx.lineWidth = w;
    ctx.strokeRect(w / 2, w / 2, size - w, size - w);
  }
  return ctx.getImageData(0, 0, size, size);
}

function point(lonlat: LonLat, props: Record<string, string> = {}) {
  return { type: "Feature" as const, geometry: { type: "Point" as const, coordinates: lonlat }, properties: props };
}

export default function MapView({
  mode,
  route,
  barriers,
  origin,
  destination,
  overlayOn,
  onToggleOverlay,
  standardOn,
  onToggleStandard,
  placing,
  prompt,
  onPlace,
  draft,
  onDraftMove,
  reports,
  focus,
  children,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const pinRef = useRef<Marker | null>(null);

  // Handlers change every render; the map's listeners read the latest through refs.
  const placeRef = useRef(onPlace);
  const dragRef = useRef(onDraftMove);
  const placingRef = useRef(placing);
  useEffect(() => {
    placeRef.current = onPlace;
    dragRef.current = onDraftMove;
    placingRef.current = placing;
  });

  // ---- create the map once --------------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current) return;
    const t = tokens();
    const m = new MapLibreMap({
      container: containerRef.current,
      style: BASEMAP_STYLE_URL ?? FALLBACK_STYLE,
      center: HOME_CENTER,
      zoom: HOME_ZOOM,
      dragRotate: false,
      attributionControl: { compact: true },
    });
    m.touchZoomRotate.disableRotation();

    // style.load, not load: "load" also waits for every tile in view, which can take a while (or never
    // finish on a flaky tile server), and the route layers only need the style itself.
    m.once("style.load", () => {
      m.addImage("sq-defect", squareImage(16, t.bg, { color: t.a600, width: 4 }), { pixelRatio: 2 });
      m.addImage("sq-dest", squareImage(18, t.accent), { pixelRatio: 2 });

      for (const id of ["route", "standard", "barriers", "endpoints", "reports"]) {
        m.addSource(id, { type: "geojson", data: EMPTY });
      }
      // Draw order, bottom to top: grade overlays, standard route, accessible route, barrier markers,
      // endpoints, reports. The standard route sits under the accessible one, so where they share a path
      // only the accessible line shows.
      m.addLayer({
        id: "standard-grade",
        type: "line",
        source: "standard",
        filter: [">=", ["get", "grade_pct"], 0],
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: {
          "line-width": 16,
          "line-opacity": 0.5,
          "line-color": ["interpolate", ["linear"], ["get", "grade_pct"], 3, t.a200, 12, t.a700] as ExpressionSpecification,
        },
      });
      m.addLayer({
        id: "route-grade",
        type: "line",
        source: "route",
        filter: [">=", ["get", "grade_pct"], 0],
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: {
          "line-width": 16,
          "line-opacity": 0.5,
          "line-color": ["interpolate", ["linear"], ["get", "grade_pct"], 3, t.a200, 12, t.a700] as ExpressionSpecification,
        },
      });
      m.addLayer({
        id: "standard-line",
        type: "line",
        source: "standard",
        layout: { "line-cap": "butt", "line-join": "round" },
        // Dashes are in multiples of the line width: 6px line, so about 14px on / 9px off.
        paint: { "line-width": 6, "line-color": t.ink, "line-dasharray": [2.3, 1.5] },
      });
      m.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": 8, "line-color": t.accent },
      });
      m.addLayer({
        id: "barrier-ramp",
        type: "circle",
        source: "barriers",
        filter: ["==", ["get", "kind"], "missing_ramp"],
        paint: { "circle-radius": 7, "circle-color": t.a700, "circle-stroke-width": 3, "circle-stroke-color": t.bg },
      });
      m.addLayer({
        id: "barrier-ramp-issue",
        type: "circle",
        source: "barriers",
        filter: ["==", ["get", "kind"], "ramp_issue"],
        paint: { "circle-radius": 6, "circle-color": t.bg, "circle-stroke-width": 3, "circle-stroke-color": t.a700 },
      });
      m.addLayer({
        id: "barrier-sidewalk",
        type: "symbol",
        source: "barriers",
        filter: ["==", ["get", "kind"], "bad_sidewalk"],
        layout: { "icon-image": "sq-defect", "icon-allow-overlap": true, "icon-ignore-placement": true },
      });
      m.addLayer({
        id: "endpoint-origin",
        type: "circle",
        source: "endpoints",
        filter: ["==", ["get", "role"], "origin"],
        paint: { "circle-radius": 7, "circle-opacity": 0, "circle-stroke-width": 4, "circle-stroke-color": t.ink },
      });
      m.addLayer({
        id: "endpoint-destination",
        type: "symbol",
        source: "endpoints",
        filter: ["==", ["get", "role"], "destination"],
        layout: { "icon-image": "sq-dest", "icon-allow-overlap": true, "icon-ignore-placement": true },
      });
      m.addLayer({
        id: "reports",
        type: "symbol",
        source: "reports",
        layout: { "icon-image": "sq-defect", "icon-allow-overlap": true, "icon-ignore-placement": true },
      });
      setMap(m);
    });

    m.on("click", (e) => {
      if (placingRef.current) placeRef.current(e.lngLat.lat, e.lngLat.lng);
    });

    return () => {
      pinRef.current?.remove();
      pinRef.current = null;
      m.remove();
      setMap(null);
    };
  }, []);

  // ---- route + fit ----------------------------------------------------------------------------
  const routeData = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: (route?.route.features ?? []).map((f) => ({
        ...f,
        // -1 marks "no grade note" so the overlay layer can filter on a plain number.
        properties: { ...f.properties, grade_pct: gradeFromWarnings(f.properties.warnings) ?? -1 },
      })),
    }),
    [route],
  );
  const standardData = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: (route?.standard?.route.features ?? []).map((f) => ({
        ...f,
        properties: { ...f.properties, grade_pct: gradeFromWarnings(f.properties.warnings) ?? -1 },
      })),
    }),
    [route],
  );
  useEffect(() => {
    if (!map) return;
    (map.getSource("route") as GeoJSONSource).setData(routeData);
    (map.getSource("standard") as GeoJSONSource).setData(standardData);
    if (routeData.features.length === 0) return;
    // Fit both routes, whether or not the standard one is showing, so toggling it never moves the map.
    const bounds = new LngLatBounds();
    for (const f of [...routeData.features, ...standardData.features]) {
      for (const c of f.geometry.coordinates) bounds.extend(c);
    }
    // No animation: the design specifies none, and it keeps the map calm for motion-sensitive users.
    map.fitBounds(bounds, { padding: 90, maxZoom: 17, animate: false });
  }, [map, routeData, standardData]);

  // ---- markers --------------------------------------------------------------------------------
  useEffect(() => {
    if (!map) return;
    (map.getSource("barriers") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: barriers.map((b) => point(b.lonlat, { kind: b.kind })),
    });
  }, [map, barriers]);

  useEffect(() => {
    if (!map) return;
    const features = [];
    if (origin) features.push(point(origin, { role: "origin" }));
    if (destination) features.push(point(destination, { role: "destination" }));
    (map.getSource("endpoints") as GeoJSONSource).setData({ type: "FeatureCollection", features });
  }, [map, origin, destination]);

  useEffect(() => {
    if (!map) return;
    (map.getSource("reports") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: reports.map((r) => point([r.lon, r.lat], { category: r.category })),
    });
  }, [map, reports]);

  useEffect(() => {
    if (!map) return;
    const show = (on: boolean) => (on ? "visible" : "none");
    for (const id of ["route-grade", "barrier-ramp", "barrier-ramp-issue", "barrier-sidewalk"]) {
      map.setLayoutProperty(id, "visibility", show(overlayOn));
    }
    map.setLayoutProperty("standard-line", "visibility", show(standardOn));
    map.setLayoutProperty("standard-grade", "visibility", show(standardOn && overlayOn));
  }, [map, overlayOn, standardOn]);

  // ---- pan to a barrier chosen in the list ----------------------------------------------------
  useEffect(() => {
    if (!map || !focus) return;
    map.jumpTo({ center: focus.lonlat, zoom: Math.max(map.getZoom(), 17) });
  }, [map, focus]);

  // ---- draggable hazard pin -------------------------------------------------------------------
  const draftLat = draft?.lat ?? null;
  const draftLon = draft?.lon ?? null;
  useEffect(() => {
    if (!map) return;
    if (draftLat === null || draftLon === null) {
      pinRef.current?.remove();
      pinRef.current = null;
      return;
    }
    if (pinRef.current) {
      pinRef.current.setLngLat([draftLon, draftLat]);
      return;
    }
    const el = document.createElement("div");
    el.className = "cc-pin";
    el.innerHTML = '<div class="cc-pin__square"></div>';
    const pin = new Marker({ element: el, draggable: true }).setLngLat([draftLon, draftLat]).addTo(map);
    pin.on("dragend", () => {
      const p = pin.getLngLat();
      dragRef.current(p.lat, p.lng);
    });
    pinRef.current = pin;
  }, [map, draftLat, draftLon]);

  function useMapCentre() {
    const c = map?.getCenter();
    if (c) onPlace(c.lat, c.lng);
  }

  const zoom = (
    <div className="cc-zoom" role="group" aria-label="Zoom">
      <button type="button" aria-label="Zoom in" onClick={() => map?.zoomIn({ duration: 0 })}>
        <Plus size={19} strokeWidth={2.5} aria-hidden />
      </button>
      <button type="button" aria-label="Zoom out" onClick={() => map?.zoomOut({ duration: 0 })}>
        <Minus size={19} strokeWidth={2.5} aria-hidden />
      </button>
    </div>
  );

  return (
    <div className="cc-mapwrap">
      <div ref={containerRef} className={`cc-map${placing ? " cc-map--picking" : ""}`} />

      <div className="cc-overlay cc-overlay--tl">
        <span
          className="cc-mapchip cc-mapchip--accent"
          title="ClearCurb v1.0 only routes within Lower Manhattan, below about 14th St."
        >
          V1.0 · Lower Manhattan only
        </span>
        {mode === "plan" && (
          <>
            <button type="button" className="cc-mapchip" aria-pressed={overlayOn} onClick={onToggleOverlay}>
              Barrier overlay {overlayOn ? "on" : "off"}
            </button>
            <button type="button" className="cc-mapchip" aria-pressed={standardOn} onClick={onToggleStandard}>
              Standard route {standardOn ? "on" : "off"}
            </button>
          </>
        )}
      </div>

      {prompt && (
        <div className="cc-overlay cc-pickbar" role="status">
          <span>{prompt.text}</span>
          <button type="button" onClick={useMapCentre} disabled={!map}>
            Use map centre
          </button>
          <button type="button" onClick={prompt.onCancel}>
            Cancel
          </button>
        </div>
      )}

      <div className={`cc-overlay ${mode === "plan" ? "cc-overlay--tr" : "cc-overlay--br"}`}>{zoom}</div>

      <div className="cc-overlay cc-overlay--bl">
        <Legend mode={mode} standardOn={standardOn} />
      </div>

      {children}
    </div>
  );
}

function Legend({ mode, standardOn }: { mode: "plan" | "report"; standardOn: boolean }) {
  return (
    <div className="cc-legend" role="group" aria-label="Map legend">
      {mode === "plan" ? (
        <>
          <span className="cc-legend__item">
            <span className="cc-legend__swatch cc-swatch--route" /> Accessible route
          </span>
          {standardOn && (
            <span className="cc-legend__item">
              <span className="cc-legend__swatch cc-swatch--standard" /> Standard route
            </span>
          )}
          <span className="cc-legend__item">
            <span className="cc-legend__swatch cc-swatch--ramp" /> No verified ramp
          </span>
          <span className="cc-legend__item">
            <span className="cc-legend__swatch cc-swatch--ramp-issue" /> Ramp issue
          </span>
          <span className="cc-legend__item">
            <span className="cc-legend__swatch cc-swatch--sidewalk" /> Sidewalk defects
          </span>
          <span className="cc-legend__item">
            <span className="cc-legend__swatch cc-swatch--grade" /> Grade severity
          </span>
        </>
      ) : (
        <>
          <span className="cc-legend__item">
            <span className="cc-legend__swatch cc-swatch--route" /> Your route
          </span>
          <span className="cc-legend__item">
            <span className="cc-legend__swatch cc-swatch--sidewalk" /> Unverified report
          </span>
        </>
      )}
    </div>
  );
}
