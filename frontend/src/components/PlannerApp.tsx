"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { describeError, getHealth, getProfiles, getRoute, type RouteParams } from "@/lib/api";
import { analyze } from "@/lib/route-metrics";
import type { Report, ReportCategory, ReportDraft } from "@/lib/reports";
import type { ApiProfile, Barrier, LonLat, Place, RouteResponse, Strictness } from "@/lib/types";
import { coordLabel, DEFAULT_DESTINATION, DEFAULT_ORIGIN } from "@/lib/ui-copy";
import ComparisonBand, { type BandState } from "./ComparisonBand";
import PlanRail, { type HealthState } from "./PlanRail";
import { ReportPopover, ReportRail } from "./ReportPanels";
import TopBar, { type PickTarget } from "./TopBar";

// maplibre-gl needs the browser, so the map is only loaded on the client.
const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div className="cc-mapwrap" aria-busy="true" />,
});

interface Settled {
  params: RouteParams;
  data?: RouteResponse;
  error?: { message: string; status: number | null };
}

export default function PlannerApp() {
  const [mode, setMode] = useState<"plan" | "report">("plan");

  // backend status: GET /api/health, GET /api/profiles
  const [health, setHealth] = useState<HealthState>({ status: "checking" });
  const [profiles, setProfiles] = useState<ApiProfile[] | null>(null);
  const [profilesError, setProfilesError] = useState<string | null>(null);

  // trip
  const [chosenProfile, setChosenProfile] = useState<string | null>(null);
  const [strictness, setStrictness] = useState<Strictness>("hard");
  const [origin, setOrigin] = useState<Place | null>(DEFAULT_ORIGIN);
  const [destination, setDestination] = useState<Place | null>(DEFAULT_DESTINATION);
  const [pickTarget, setPickTarget] = useState<PickTarget | null>(null);
  const [overlayOn, setOverlayOn] = useState(true);
  const [standardOn, setStandardOn] = useState(true);
  const [focus, setFocus] = useState<{ lonlat: LonLat; nonce: number } | null>(null);

  // route: GET /api/route
  const [settled, setSettled] = useState<Settled | null>(null);
  const [startedFor, setStartedFor] = useState<RouteParams | null>(null);

  // hazard reports (in memory only; there is no reports endpoint yet)
  const [draft, setDraft] = useState<ReportDraft | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const reportSeq = useRef(0);

  // ---- health + profiles, once ----------------------------------------------------------------
  useEffect(() => {
    const ac = new AbortController();
    getHealth(ac.signal)
      .then((h) => setHealth({ status: "up", graphLoaded: h.graph_loaded }))
      .catch(() => {
        if (!ac.signal.aborted) setHealth({ status: "down" });
      });
    getProfiles(ac.signal)
      .then(setProfiles)
      .catch((e) => {
        if (!ac.signal.aborted) setProfilesError(describeError(e).message);
      });
    return () => ac.abort();
  }, []);

  const profile = chosenProfile ?? profiles?.find((p) => p.key === "manual")?.key ?? profiles?.[0]?.key ?? null;

  // ---- route request --------------------------------------------------------------------------
  const params = useMemo<RouteParams | null>(
    () =>
      origin && destination && profile
        ? {
            from: { lat: origin.lat, lon: origin.lon },
            to: { lat: destination.lat, lon: destination.lon },
            profile,
            // "Soft" lets the router cross where no curb ramp could be verified, at a heavy penalty.
            allowUnverifiedCrossings: strictness === "soft",
          }
        : null,
    [origin, destination, profile, strictness],
  );

  useEffect(() => {
    if (!params) return;
    const ac = new AbortController();
    getRoute(params, ac.signal)
      .then((data) => setSettled({ params, data }))
      .catch((e) => {
        if (!ac.signal.aborted) setSettled({ params, error: describeError(e) });
      });
    return () => ac.abort();
  }, [params]);

  const current = settled && settled.params === params ? settled : null;
  const loading = params !== null && current === null;
  // While a new request is in flight keep showing the previous route, dimmed, instead of blanking the map.
  const route: RouteResponse | null = params === null ? null : (current ?? settled)?.data ?? null;
  const error = current?.error ?? null;

  const analysis = useMemo(() => (route ? analyze(route) : null), [route]);
  const barriers = useMemo<Barrier[]>(() => analysis?.accessible ?? [], [analysis]);
  const avoided = useMemo<Barrier[]>(() => analysis?.avoided ?? [], [analysis]);
  const comparison = analysis?.comparison ?? null;
  // Markers on the map: the accessible route's, plus what it avoids while the standard route is showing.
  const mapBarriers = useMemo<Barrier[]>(() => (standardOn ? [...barriers, ...avoided] : barriers), [barriers, avoided, standardOn]);

  const band: BandState = !params
    ? { kind: "idle" }
    : error
      ? { kind: "error", message: error.message, canRelax: strictness === "hard" && error.status === 404 }
      : loading
        ? { kind: "loading", stale: comparison }
        : comparison
          ? { kind: "ready", comparison }
          : { kind: "loading", stale: null };

  // ---- map interaction ------------------------------------------------------------------------
  function place(lat: number, lon: number) {
    if (mode === "report") {
      setDraft((d) => ({ category: null, note: "", ...d, lat, lon }));
      return;
    }
    const p: Place = { lat, lon, label: coordLabel(lat, lon) };
    if (pickTarget === "origin") setOrigin(p);
    else if (pickTarget === "destination") setDestination(p);
    setPickTarget(null);
  }

  function pick(t: PickTarget) {
    setPickTarget((cur) => (cur === t ? null : t));
  }

  function startReport() {
    setPickTarget(null);
    setMode("report");
  }

  function endReport() {
    setDraft(null);
    setMode("plan");
  }

  function submitReport() {
    if (!draft?.category) return;
    const category: ReportCategory = draft.category;
    reportSeq.current += 1;
    setReports((rs) => [
      {
        id: `local-${reportSeq.current}`,
        category,
        lat: draft.lat,
        lon: draft.lon,
        note: draft.note.trim(),
        filedAt: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
        status: "unverified",
      },
      ...rs,
    ]);
    setDraft(null); // optimistic: the marker is on the map straight away
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (mode === "report") {
        setDraft(null);
        setMode("plan");
      } else {
        setPickTarget(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode]);

  // ---- derived props for the map --------------------------------------------------------------
  // Once routed, draw the endpoints where the route really starts and ends (snapped to the sidewalk network).
  const originPoint: LonLat | null = route?.snapped.start.lonlat ?? (origin ? [origin.lon, origin.lat] : null);
  const destinationPoint: LonLat | null = route?.snapped.end.lonlat ?? (destination ? [destination.lon, destination.lat] : null);
  const snapHint = (ft: number | undefined) => (ft && ft > 25 ? `snapped ${ft} ft` : null);

  const prompt =
    mode === "report"
      ? draft
        ? null
        : { text: "Click the map to place the hazard", onCancel: endReport }
      : pickTarget
        ? { text: `Click the map to set ${pickTarget === "origin" ? "FROM" : "TO"}`, onCancel: () => setPickTarget(null) }
        : null;

  return (
    <div className="cc-app">
      <TopBar
        mode={mode}
        origin={origin}
        destination={destination}
        originHint={pickTarget === "origin" ? "Click the map" : snapHint(route?.snapped.start.snap_distance_ft)}
        destinationHint={pickTarget === "destination" ? "Click the map" : snapHint(route?.snapped.end.snap_distance_ft)}
        pickTarget={pickTarget}
        onPick={pick}
        onStartReport={startReport}
        onEndReport={endReport}
        hasDraft={draft !== null}
      />

      <div className="cc-body">
        {mode === "plan" ? (
          <PlanRail
            health={health}
            profiles={profiles}
            profilesError={profilesError}
            profile={profile}
            onProfile={setChosenProfile}
            strictness={strictness}
            onStrictness={setStrictness}
            barriers={barriers}
            avoided={avoided}
            hasStandard={route?.standard != null}
            hasRoute={route !== null}
            routeFailed={error !== null}
            onFocusBarrier={(b) => setFocus({ lonlat: b.lonlat, nonce: (focus?.nonce ?? 0) + 1 })}
          />
        ) : (
          <ReportRail reports={reports} />
        )}

        <div className="cc-main">
          <MapView
            mode={mode}
            route={route}
            barriers={mapBarriers}
            origin={originPoint}
            destination={destinationPoint}
            overlayOn={overlayOn}
            onToggleOverlay={() => setOverlayOn((v) => !v)}
            standardOn={standardOn}
            onToggleStandard={() => setStandardOn((v) => !v)}
            placing={mode === "report" || pickTarget !== null}
            prompt={prompt}
            onPlace={place}
            draft={draft ? { lat: draft.lat, lon: draft.lon } : null}
            onDraftMove={(lat, lon) => setDraft((d) => (d ? { ...d, lat, lon } : d))}
            reports={mode === "report" ? reports : []}
            focus={focus}
          >
            {mode === "report" && draft && (
              <ReportPopover
                draft={draft}
                onCategory={(category) => setDraft((d) => (d ? { ...d, category } : d))}
                onNote={(note) => setDraft((d) => (d ? { ...d, note } : d))}
                onSubmit={submitReport}
              />
            )}
          </MapView>

          {mode === "plan" && (
            <ComparisonBand
              state={band}
              started={startedFor === params && params !== null}
              onStart={() => setStartedFor(params)}
              onRelax={() => setStrictness("soft")}
            />
          )}
        </div>
      </div>
    </div>
  );
}
