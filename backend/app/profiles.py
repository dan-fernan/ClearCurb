"""Mobility profiles and the edge cost function used for routing.

Cost is in feet-equivalents: a plain, flat, clean sidewalk edge costs exactly its length, and every
barrier either multiplies that or adds a fixed penalty. An edge that cannot be used returns ``None``.

The numbers below are starting assumptions, not clinical guidance. They are anchored to the ADA
figures (5% for a walkable route, 8.33% ramp running slope, 2% cross slope, 0.5 in curb lip) and
loosened or tightened per profile. Tune them against real users' feedback; every knob is a field
on ``Profile`` and profiles are immutable, so use ``dataclasses.replace`` to make a variant.

Edge attributes read (all produced by backend/scripts/attach_attributes.py):
    sidewalk/step:  edge_type, length_ft, grade_pct (signed, u -> v), grade_reliable, n_open_viol,
                    viol_trip_hazard, viol_broken, viol_slope, viol_undermined, viol_sw_missing
    crossing:       ramp_status ('both'|'one'|'none'), raised, ramp_slope_max, ramp_cross_slope_max,
                    lip_in_max
Missing values are treated as "no information" and never block an edge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping

# Segments shorter than this never hard-block on grade: a few feet of elevation noise swings the value.
MIN_BLOCKING_LENGTH_FT = 60


@dataclass(frozen=True)
class Profile:
    key: str
    label: str

    # Sidewalk grade (percent, absolute unless noted)
    grade_ok: float
    grade_block: float | None        # impassable above this on segments >= 60 ft
    grade_weight: float              # cost multiplier added per percent above grade_ok
    uphill_weight: float             # extra multiplier per percent above grade_ok when travelling uphill

    # Curb ramps on crossings (feet-equivalents added per unit above the limit)
    ramp_slope_ok: float
    ramp_slope_block: float | None
    ramp_slope_weight: float         # per percent of running slope
    cross_slope_ok: float
    cross_slope_weight: float        # per percent of cross slope
    lip_ok_in: float
    lip_block_in: float | None
    lip_weight: float                # per inch of curb lip

    # Crossings without a verified ramp, and step streets
    no_ramp_blocks: bool             # False: the curb can be stepped, so it is only penalised
    no_ramp_penalty_ft: float
    step_multiplier: float | None    # None: step streets are impassable
    crossing_base_ft: float          # fixed cost of any street crossing (waiting, crossing time)

    # Open sidewalk violations on the edge (added to the cost multiplier)
    viol_weight: float
    trip_weight: float
    broken_weight: float
    undermined_weight: float
    slope_defect_weight: float
    sw_missing_weight: float

    allow_unverified: bool = False   # True: crossings without a verified ramp are penalised, not blocked


MANUAL = Profile(
    key="manual", label="Manual wheelchair",
    grade_ok=3.0, grade_block=8.33, grade_weight=0.35, uphill_weight=0.5,
    ramp_slope_ok=8.33, ramp_slope_block=15.0, ramp_slope_weight=20.0,
    cross_slope_ok=2.0, cross_slope_weight=20.0,
    lip_ok_in=0.5, lip_block_in=2.0, lip_weight=60.0,
    no_ramp_blocks=True, no_ramp_penalty_ft=500.0, step_multiplier=None, crossing_base_ft=30.0,
    viol_weight=0.3, trip_weight=0.5, broken_weight=0.2, undermined_weight=0.3,
    slope_defect_weight=0.2, sw_missing_weight=4.0,
)

POWER = Profile(
    key="power", label="Power wheelchair",
    grade_ok=5.0, grade_block=12.0, grade_weight=0.15, uphill_weight=0.1,
    ramp_slope_ok=8.33, ramp_slope_block=20.0, ramp_slope_weight=8.0,
    cross_slope_ok=2.0, cross_slope_weight=10.0,
    lip_ok_in=1.0, lip_block_in=3.0, lip_weight=25.0,
    no_ramp_blocks=True, no_ramp_penalty_ft=500.0, step_multiplier=None, crossing_base_ft=30.0,
    viol_weight=0.15, trip_weight=0.3, broken_weight=0.15, undermined_weight=0.2,
    slope_defect_weight=0.1, sw_missing_weight=4.0,
)

WALKER = Profile(
    key="walker", label="Walker / crutches",
    grade_ok=4.0, grade_block=12.0, grade_weight=0.3, uphill_weight=0.4,
    ramp_slope_ok=8.33, ramp_slope_block=None, ramp_slope_weight=12.0,
    cross_slope_ok=2.0, cross_slope_weight=15.0,
    lip_ok_in=0.5, lip_block_in=3.0, lip_weight=50.0,
    no_ramp_blocks=False, no_ramp_penalty_ft=400.0, step_multiplier=8.0, crossing_base_ft=50.0,
    viol_weight=0.3, trip_weight=0.8, broken_weight=0.4, undermined_weight=0.3,
    slope_defect_weight=0.3, sw_missing_weight=3.0,
)

PROFILES: dict[str, Profile] = {p.key: p for p in (MANUAL, POWER, WALKER)}


def _num(attrs: Mapping, key: str) -> float | None:
    v = attrs.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _flag(attrs: Mapping, key: str) -> bool:
    v = attrs.get(key)
    return bool(v) and not (isinstance(v, float) and math.isnan(v))


def evaluate_edge(attrs: Mapping, profile: Profile, forward: bool = True) -> tuple[float | None, list[str]]:
    """Return (cost, notes). cost is None when the edge is impassable; notes say why or what was penalised.

    ``forward`` is True when travelling u -> v, which decides whether a signed grade is uphill.
    Notes starting with "blocked:" explain a block.
    """
    length = float(attrs["length_ft"])
    kind = attrs["edge_type"]
    notes: list[str] = []

    if kind == "link":
        return 0.0, notes
    if kind == "step":
        if profile.step_multiplier is None:
            return None, ["blocked: step street"]
        return length * profile.step_multiplier, ["step street"]
    if kind == "crossing":
        return _crossing_cost(attrs, profile, length, notes)
    return _sidewalk_cost(attrs, profile, length, forward, notes)


def _sidewalk_cost(attrs, profile: Profile, length, forward, notes):
    mult = 1.0
    grade = _num(attrs, "grade_pct")
    if grade is not None:
        g_abs = abs(grade)
        g_up = grade if forward else -grade
        if (profile.grade_block is not None and g_abs > profile.grade_block
                and _flag(attrs, "grade_reliable") and length >= MIN_BLOCKING_LENGTH_FT):
            return None, [f"blocked: grade {g_abs:.1f}%"]
        if g_abs > profile.grade_ok:
            mult += profile.grade_weight * (g_abs - profile.grade_ok)
            notes.append(f"grade {g_abs:.1f}%")
        if g_up > profile.grade_ok:
            mult += profile.uphill_weight * (g_up - profile.grade_ok)

    n_open = _num(attrs, "n_open_viol") or 0
    if n_open > 0:
        mult += profile.viol_weight
        notes.append(f"{int(n_open)} open violation(s)")
        for col, weight, label in (
            ("viol_trip_hazard", profile.trip_weight, "trip hazard"),
            ("viol_broken", profile.broken_weight, "broken pavement"),
            ("viol_undermined", profile.undermined_weight, "undermined"),
            ("viol_slope", profile.slope_defect_weight, "sloped defect"),
            ("viol_sw_missing", profile.sw_missing_weight, "missing sidewalk"),
        ):
            if (_num(attrs, col) or 0) > 0:
                mult += weight
                notes.append(label)
    return length * mult, notes


def _crossing_cost(attrs, profile: Profile, length, notes):
    cost = length + profile.crossing_base_ft
    if _flag(attrs, "raised"):
        notes.append("raised crosswalk")
        return cost, notes

    status = attrs.get("ramp_status")
    if status in ("one", "none"):
        if profile.no_ramp_blocks and not profile.allow_unverified:
            return None, [f"blocked: ramp {'missing' if status == 'none' else 'found at one end only'}"]
        cost += profile.no_ramp_penalty_ft
        notes.append("no verified ramp")

    slope = _num(attrs, "ramp_slope_max")
    if slope is not None:
        if profile.ramp_slope_block is not None and slope > profile.ramp_slope_block:
            return None, [f"blocked: ramp slope {slope:.1f}%"]
        if slope > profile.ramp_slope_ok:
            cost += profile.ramp_slope_weight * (slope - profile.ramp_slope_ok)
            notes.append(f"ramp slope {slope:.1f}%")

    cross = _num(attrs, "ramp_cross_slope_max")
    if cross is not None and cross > profile.cross_slope_ok:
        cost += profile.cross_slope_weight * (cross - profile.cross_slope_ok)
        notes.append(f"cross slope {cross:.1f}%")

    lip = _num(attrs, "lip_in_max")
    if lip is not None:
        if profile.lip_block_in is not None and lip > profile.lip_block_in:
            return None, [f"blocked: curb lip {lip:.1f} in"]
        if lip > profile.lip_ok_in:
            cost += profile.lip_weight * (lip - profile.lip_ok_in)
            notes.append(f"curb lip {lip:.1f} in")
    return cost, notes


def edge_cost(attrs: Mapping, profile: Profile, forward: bool = True) -> float | None:
    return evaluate_edge(attrs, profile, forward)[0]


def with_unverified_crossings(profile: Profile) -> Profile:
    """Variant that routes over crossings with no verified ramp, at a heavy penalty, instead of blocking."""
    return replace(profile, allow_unverified=True)
