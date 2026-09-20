import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .profiles import PROFILES
from .routing import NoRoute, OutsideCoverage, RouteEngine, SamePoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine = RouteEngine.load()
        engine.warm()
        app.state.engine = engine
    except FileNotFoundError:
        # Health and profile endpoints still work; /api/route explains what is missing.
        app.state.engine = None
    yield


# Comma-separated list. Only needed if a browser calls the API directly; the Next.js rewrite is server to server.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app = FastAPI(title="ClearCurb API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "graph_loaded": app.state.engine is not None}


@app.get("/api/profiles")
def profiles() -> list[dict[str, str]]:
    return [{"key": p.key, "label": p.label} for p in PROFILES.values()]


@app.get("/api/route")
def route(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lon: float = Query(..., ge=-180, le=180),
    profile: str = Query("manual"),
    allow_unverified_crossings: bool = Query(
        False, description="Also route over crossings where no curb ramp could be verified."
    ),
) -> dict:
    """Cheapest accessible route as GeoJSON, with a summary and per-segment warnings.

    ``standard`` is the plain shortest path over the same graph, described the same way, so a client can
    show what the accessible route avoids. It is null only if the two points are not connected at all.
    """
    engine: RouteEngine | None = app.state.engine
    if engine is None:
        raise HTTPException(503, "Routing graph not built. Run backend/scripts/attach_attributes.py.")
    if profile not in PROFILES:
        raise HTTPException(422, f"Unknown profile '{profile}'. Options: {', '.join(PROFILES)}")
    try:
        result = engine.route((from_lat, from_lon), (to_lat, to_lon), profile, allow_unverified_crossings)
    except (OutsideCoverage, SamePoint) as e:
        raise HTTPException(422, str(e))
    except NoRoute as e:
        hint = "" if allow_unverified_crossings else " Try allow_unverified_crossings=true."
        raise HTTPException(404, f"{e}{hint}")
    return {
        "route": result.feature_collection,
        "summary": result.summary,
        "snapped": result.snapped,
        "standard": result.standard,
    }
