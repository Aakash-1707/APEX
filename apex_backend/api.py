"""
APEX Backend API — OpenF1 Edition
==================================
FastAPI server that proxies OpenF1 REST API and runs Monte Carlo predictions.

Run:
    pip install fastapi uvicorn httpx numpy
    uvicorn api:app --reload --port 8000

Endpoints:
    GET  /api/health                                    → server status
    GET  /api/calendar                                  → 2026 race calendar (from OpenF1)
    GET  /api/sessions/{meeting_key}                    → sessions for a meeting
    GET  /api/drivers/{session_key}                     → driver list
    GET  /api/telemetry/{session_key}/{driver_number}   → car telemetry + location
    GET  /api/laps/{session_key}/{driver_number}        → lap times + sectors
    GET  /api/stints/{session_key}                      → tyre stint data
    GET  /api/result/{session_key}                      → session result
    GET  /api/weather/{session_key}                     → weather data
    GET  /api/starting_grid/{session_key}               → starting grid
    POST /api/predict                                   → run Monte Carlo prediction
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json
import os
import hashlib
import httpx
import time as _time
from datetime import datetime, timezone

import model_core as mc

OPENF1_BASE = "https://api.openf1.org/v1"

app = FastAPI(title="APEX F1 API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── IN-MEMORY CACHE ─────────────────────────────────────────────────────────
# Caches OpenF1 responses to avoid 429 rate limit errors.
# TTL: 300s (5 min) for most data, 3600s (1 hour) for calendar/meetings.

_MEM_CACHE: dict[str, tuple[float, any]] = {}
_DEFAULT_TTL = 300  # 5 minutes
_LONG_TTL = 3600    # 1 hour (for calendar, sessions)


def _cache_get(key: str) -> Optional[any]:
    if key in _MEM_CACHE:
        ts, data = _MEM_CACHE[key]
        if _time.time() - ts < _DEFAULT_TTL:
            return data
        del _MEM_CACHE[key]
    return None


def _cache_set(key: str, data: any, ttl: int = _DEFAULT_TTL):
    _MEM_CACHE[key] = (_time.time(), data)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _openf1(endpoint: str, params: dict = None, ttl: int = _DEFAULT_TTL) -> list | dict:
    """Fetch data from OpenF1 API with caching and retry."""
    # Build cache key
    cache_key = f"{endpoint}|{json.dumps(params or {}, sort_keys=True)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{OPENF1_BASE}/{endpoint}"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    _time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                
                # Handle dictionary responses (usually error details)
                if isinstance(data, dict) and "detail" in data:
                    print(f"OpenF1 API Notice: {data['detail']}")
                    return []
                
                _cache_set(cache_key, data, ttl)
                return data
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code in [401, 403, 404]:
                print(f"OpenF1 API Notice ({status_code}): {e.response.text}")
                return []
            if attempt < max_retries - 1:
                _time.sleep(1)
                continue
            raise
    return []


# ─── PREDICTION + CIRCUIT STATS CACHE ─────────────────────────────────────────

CACHE_DIR = os.path.join(os.path.dirname(__file__), "prediction_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _prediction_cache_key(meeting_key: int, session_key: Optional[int], race_session_key: Optional[int], n_sims: int, source_mode: str) -> str:
    """Include quali + race session + source mode so different inputs get separate caches."""
    raw = f"openf1_{meeting_key}_{session_key or 0}_{race_session_key or 0}_{n_sims}_{source_mode}"
    return hashlib.md5(raw.encode()).hexdigest()


def _load_cache(key: str) -> Optional[dict]:
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _save_cache(key: str, data: dict):
    path = os.path.join(CACHE_DIR, f"{key}.json")
    with open(path, "w") as f:
        json.dump(data, f)


def _get_circuit_stats_from_openf1(circuit_key: int) -> Optional[dict]:
    """
    Estimate SC / VSC / rain probabilities for a circuit from recent race history.
    Uses OpenF1 'sessions', 'race_control' and 'weather' endpoints across 2023–2025.
    """
    years = [2023, 2024, 2025]
    race_sessions = []
    for year in years:
        try:
            sess = _openf1("sessions", {
                "year": year,
                "circuit_key": circuit_key,
                "session_type": "Race",
            })
            if isinstance(sess, list):
                race_sessions.extend(sess)
        except Exception:
            continue

    if not race_sessions:
        return None

    total_races = 0
    sc_races = 0
    vsc_races = 0
    rain_races = 0

    for s in race_sessions:
        skey = s.get("session_key")
        if not skey:
            continue
        total_races += 1

        # Race control flags
        try:
            rc = _openf1("race_control", {"session_key": skey})
        except Exception:
            rc = []
        if isinstance(rc, list):
            flags = [str(e.get("flag", "")).upper() for e in rc]
            has_sc = any("SAFETY CAR" in f and "VIRTUAL" not in f for f in flags)
            has_vsc = any("VIRTUAL SAFETY CAR" in f for f in flags)
            if has_sc:
                sc_races += 1
            if has_vsc:
                vsc_races += 1

        # Weather (rainfall flag)
        try:
            weather = _openf1("weather", {"session_key": skey})
        except Exception:
            weather = []
        if isinstance(weather, list):
            if any(w.get("rainfall") for w in weather):
                rain_races += 1

    if total_races == 0:
        return None

    stats = {
        "sc_prob": sc_races / total_races,
        "vsc_prob": vsc_races / total_races,
        "rain_prob": rain_races / total_races,
        "n_races": total_races,
    }
    return stats


# ─── HEALTH ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "data_source": "openf1"}


# ─── CALENDAR ─────────────────────────────────────────────────────────────────

@app.get("/api/calendar")
def get_calendar(year: int = Query(2026)):
    """Fetch race calendar from OpenF1, excluding testing events."""
    meetings = []
    try:
        meetings = _openf1("meetings", {"year": year})
    except httpx.HTTPStatusError as e:
        print(f"OpenF1 calendar error for year={year}: {e.response.status_code} - {e.response.text[:200]}")
        if year == 2026:
            # Fallback when OpenF1 returns 502/5xx for 2026
            return [
                {"meeting_key": 1280, "name": "Chinese Grand Prix", "circuit_short_name": "Shanghai", "date_start": "2026-03-13T00:00:00", "date_end": "2026-03-15T23:59:59", "mode": "live"},
                {"meeting_key": 1281, "name": "Australian Grand Prix", "circuit_short_name": "Melbourne", "date_start": "2026-03-27T00:00:00", "date_end": "2026-03-29T23:59:59", "mode": "upcoming"}
            ]
        meetings = []
    except Exception as e:
        print(f"OpenF1 calendar error: {e}")
        if year == 2026:
            return [
                {"meeting_key": 1280, "name": "Chinese Grand Prix", "circuit_short_name": "Shanghai", "date_start": "2026-03-13T00:00:00", "date_end": "2026-03-15T23:59:59", "mode": "live"},
                {"meeting_key": 1281, "name": "Australian Grand Prix", "circuit_short_name": "Melbourne", "date_start": "2026-03-27T00:00:00", "date_end": "2026-03-29T23:59:59", "mode": "upcoming"}
            ]
        meetings = []

    if not isinstance(meetings, list):
        print(f"Warning: Expected list from OpenF1, got {type(meetings)}")
        meetings = []

    now = datetime.now(timezone.utc)
    output = []

    # Fallback if meetings is empty (due to API restrictions)
    if not meetings and year == 2026:
        return [
            {"meeting_key": 1280, "name": "Chinese Grand Prix", "circuit_short_name": "Shanghai", "date_start": "2026-03-13T00:00:00", "date_end": "2026-03-15T23:59:59", "mode": "live"},
            {"meeting_key": 1281, "name": "Australian Grand Prix", "circuit_short_name": "Melbourne", "date_start": "2026-03-27T00:00:00", "date_end": "2026-03-29T23:59:59", "mode": "upcoming"}
        ]

    for m in meetings:
        # Skip pre-season testing
        name = m.get("meeting_name", "")
        if "Testing" in name or "Test" in name:
            continue

        date_end = datetime.fromisoformat(m["date_end"].replace("Z", "+00:00"))
        date_start = datetime.fromisoformat(m["date_start"].replace("Z", "+00:00"))

        if date_end.tzinfo is None:
            date_end = date_end.replace(tzinfo=timezone.utc)
        if date_start.tzinfo is None:
            date_start = date_start.replace(tzinfo=timezone.utc)

        if date_end < now:
            mode = "past"
        elif date_start <= now <= date_end:
            mode = "live"
        else:
            mode = "upcoming"

        output.append({
            "meeting_key":  m["meeting_key"],
            "name":         m["meeting_name"],
            "official_name": m.get("meeting_official_name", ""),
            "location":     m.get("location", ""),
            "country_code": m.get("country_code", ""),
            "country_name": m.get("country_name", ""),
            "country_flag": m.get("country_flag", ""),
            "circuit_key":  m.get("circuit_key"),
            "circuit_short_name": m.get("circuit_short_name", ""),
            "circuit_type": m.get("circuit_type", ""),
            "circuit_image": m.get("circuit_image", ""),
            "date_start":   m["date_start"],
            "date_end":     m["date_end"],
            "gmt_offset":   m.get("gmt_offset", ""),
            "year":         year,
            "mode":         mode,
        })

    return output


# ─── SESSIONS ─────────────────────────────────────────────────────────────────

@app.get("/api/sessions/{meeting_key}")
def get_sessions(meeting_key: int):
    """Get all sessions for a meeting (FP1, Quali, Sprint, Race, etc.)."""
    try:
        sessions = _openf1("sessions", {"meeting_key": meeting_key})
    except Exception:
        sessions = []

    if not isinstance(sessions, list):
        sessions = []

    # Fallback for Chinese GP (Meeting 1280) if API is restricted — use real OpenF1 session keys
    if not sessions and meeting_key == 1280:
        sessions = [
            {"session_key": 11235, "session_name": "Practice 1", "session_type": "Practice", "date_start": "2026-03-13T03:30:00+00:00", "date_end": "2026-03-13T04:30:00+00:00"},
            {"session_key": 11236, "session_name": "Sprint Qualifying", "session_type": "Qualifying", "date_start": "2026-03-13T07:30:00+00:00", "date_end": "2026-03-13T08:14:00+00:00"},
            {"session_key": 11240, "session_name": "Sprint", "session_type": "Race", "date_start": "2026-03-14T03:00:00+00:00", "date_end": "2026-03-14T04:00:00+00:00"},
            {"session_key": 11241, "session_name": "Qualifying", "session_type": "Qualifying", "date_start": "2026-03-14T07:00:00+00:00", "date_end": "2026-03-14T08:00:00+00:00"},
            {"session_key": 11245, "session_name": "Race", "session_type": "Race", "date_start": "2026-03-15T07:00:00+00:00", "date_end": "2026-03-15T09:00:00+00:00"},
        ]

    now = datetime.now(timezone.utc)
    output = []
    for s in sessions:
        ds = s["date_start"].replace("Z", "+00:00")
        de = s["date_end"].replace("Z", "+00:00")
        date_start = datetime.fromisoformat(ds)
        date_end = datetime.fromisoformat(de)

        if date_start.tzinfo is None:
            date_start = date_start.replace(tzinfo=timezone.utc)
        if date_end.tzinfo is None:
            date_end = date_end.replace(tzinfo=timezone.utc)

        if date_end < now:
            status = "completed"
        elif date_start <= now <= date_end:
            status = "live"
        else:
            status = "upcoming"

        output.append({
            "session_key":  s["session_key"],
            "session_name": s["session_name"],
            "session_type": s["session_type"],
            "date_start":   s["date_start"],
            "date_end":     s["date_end"],
            "status":       status,
        })

    return output


# ─── DRIVERS ──────────────────────────────────────────────────────────────────

@app.get("/api/drivers/{session_key}")
def get_drivers(session_key: int):
    """Get all drivers for a session with team info."""
    drivers = _openf1("drivers", {"session_key": session_key})
    return [{
        "driver_number":  d["driver_number"],
        "full_name":      d.get("full_name", ""),
        "name_acronym":   d.get("name_acronym", ""),
        "first_name":     d.get("first_name", ""),
        "last_name":      d.get("last_name", ""),
        "team_name":      d.get("team_name", ""),
        "team_colour":    d.get("team_colour", ""),
        "headshot_url":   d.get("headshot_url", ""),
        "broadcast_name": d.get("broadcast_name", ""),
    } for d in drivers]


# ─── TELEMETRY ────────────────────────────────────────────────────────────────

def _parse_ts(s: str) -> float:
    """Parse ISO timestamp to seconds-since-epoch for comparison."""
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _merge_telemetry_by_timestamp(car_data: list, location_data: list) -> list:
    """
    Merge car_data and location by timestamp so each point has aligned x,y,speed,brake.
    Uses car_data as primary; for each car point, finds nearest location by timestamp.
    """
    if not car_data:
        return []

    # Build location lookup by timestamp (sorted)
    loc_by_ts = []
    for loc in (location_data or []):
        ts = _parse_ts(loc.get("date", ""))
        if ts > 0:
            loc_by_ts.append((ts, loc.get("x", 0), loc.get("y", 0)))
    loc_by_ts.sort(key=lambda r: r[0])

    def find_nearest_loc(target_ts: float):
        if not loc_by_ts:
            return 0, 0
        lo, hi = 0, len(loc_by_ts) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if loc_by_ts[mid][0] <= target_ts:
                lo = mid
            else:
                hi = mid
        # Pick closer of lo, hi
        d_lo = abs(loc_by_ts[lo][0] - target_ts)
        d_hi = abs(loc_by_ts[hi][0] - target_ts)
        best = lo if d_lo <= d_hi else hi
        return loc_by_ts[best][1], loc_by_ts[best][2]

    merged = []
    for c in car_data:
        ts = _parse_ts(c.get("date", ""))
        x, y = find_nearest_loc(ts)
        merged.append({
            "speed": c.get("speed", 0),
            "throttle": c.get("throttle", 0),
            "brake": c.get("brake", 0),
            "n_gear": c.get("n_gear", 0),
            "drs": c.get("drs", 0),
            "date": c.get("date", ""),
            "x": x,
            "y": y,
        })
    return merged


@app.get("/api/telemetry/{session_key}/{driver_number}")
def get_telemetry(
    session_key: int,
    driver_number: int,
    lap: Optional[int] = Query(None),
):
    """
    Fetch car telemetry + location data for a driver from OpenF1.
    Merges car_data and location by timestamp for accurate track map alignment.
    Returns ~300 points with x,y,speed,brake aligned per timestamp.
    """
    try:
        from datetime import timedelta

        laps_params = {"session_key": session_key, "driver_number": driver_number}
        if lap is not None:
            laps_params["lap_number"] = lap

        laps_data = _openf1("laps", laps_params)
        if not laps_data:
            return _empty_telemetry()

        if lap is None:
            valid_laps = [l for l in laps_data
                          if l.get("lap_duration") and l["lap_duration"] > 0
                          and not l.get("is_pit_out_lap")]
            if not valid_laps:
                valid_laps = [l for l in laps_data if l.get("lap_duration") and l["lap_duration"] > 0]
            if not valid_laps:
                return _empty_telemetry()
            target_lap = min(valid_laps, key=lambda x: x["lap_duration"])
        else:
            target_lap = laps_data[0]

        lap_number = target_lap["lap_number"]
        lap_start = target_lap.get("date_start")
        if not lap_start:
            return _empty_telemetry()

        lap_duration = target_lap.get("lap_duration", 90)
        start_dt = datetime.fromisoformat(lap_start.replace("Z", "+00:00"))
        end_dt = start_dt + timedelta(seconds=lap_duration + 1)

        car_data = _openf1("car_data", {
            "session_key": session_key,
            "driver_number": driver_number,
            "date>": lap_start,
            "date<": end_dt.isoformat(),
        })

        location_data = _openf1("location", {
            "session_key": session_key,
            "driver_number": driver_number,
            "date>": lap_start,
            "date<": end_dt.isoformat(),
        })

        if not car_data:
            return _empty_telemetry()

        # Merge by timestamp for accurate alignment
        merged = _merge_telemetry_by_timestamp(car_data, location_data)
        if not merged:
            return _empty_telemetry()

        # Sample to ~400 points for smoother track (OpenF1 ~3.7 Hz, 90s lap ≈ 333 raw)
        n_target = 400
        n_raw = len(merged)
        step = max(1, n_raw // n_target)
        sampled = merged[::step][:n_target]

        speed = [d["speed"] for d in sampled]
        throttle = [d["throttle"] for d in sampled]
        brake = [d["brake"] for d in sampled]
        gear = [d["n_gear"] for d in sampled]
        drs = [d["drs"] for d in sampled]
        timestamps = [d["date"] for d in sampled]
        x_raw = [d["x"] for d in sampled]
        y_raw = [d["y"] for d in sampled]

        # Normalize X/Y to 0-1 (preserve aspect for track shape)
        x_norm, y_norm = [], []
        if x_raw and any(x != 0 for x in x_raw) and any(y != 0 for y in y_raw):
            x_min, x_max = min(x_raw), max(x_raw)
            y_min, y_max = min(y_raw), max(y_raw)
            x_range = x_max - x_min or 1
            y_range = y_max - y_min or 1
            x_norm = [round((v - x_min) / x_range, 4) for v in x_raw]
            y_norm = [round((v - y_min) / y_range, 4) for v in y_raw]
        else:
            x_norm = x_raw
            y_norm = y_raw

        return {
            "driver_number": driver_number,
            "lap":          lap_number,
            "lap_time":     round(target_lap.get("lap_duration", 0), 3),
            "n_points":     len(sampled),
            "speed":        speed,
            "throttle":     throttle,
            "brake":        brake,
            "gear":         gear,
            "drs":          drs,
            "x":            x_norm,
            "y":            y_norm,
            "x_raw":        x_raw,
            "y_raw":        y_raw,
            "timestamps":   timestamps,
            "sectors": {
                "s1": target_lap.get("duration_sector_1"),
                "s2": target_lap.get("duration_sector_2"),
                "s3": target_lap.get("duration_sector_3"),
            },
        }
    except Exception as e:
        raise HTTPException(502, f"Telemetry fetch failed: {e}")


def _empty_telemetry() -> dict:
    return {
        "driver_number": None, "lap": None, "lap_time": None, "n_points": 0,
        "speed": [], "throttle": [], "brake": [], "gear": [], "drs": [],
        "x": [], "y": [], "x_raw": [], "y_raw": [], "timestamps": [],
        "sectors": {"s1": None, "s2": None, "s3": None},
    }


# ─── LAPS ─────────────────────────────────────────────────────────────────────

def _lap_duration(lap: dict) -> Optional[float]:
    """lap_duration from API, or computed from sectors when null (common for Sprint)."""
    d = lap.get("lap_duration")
    if d is not None and d > 0:
        return float(d)
    s1, s2, s3 = lap.get("duration_sector_1"), lap.get("duration_sector_2"), lap.get("duration_sector_3")
    if s1 is not None and s2 is not None and s3 is not None:
        return float(s1) + float(s2) + float(s3)
    return None


@app.get("/api/laps/{session_key}/{driver_number}")
def get_laps(session_key: int, driver_number: int):
    """Fetch all laps with sector times for a driver."""
    laps = _openf1("laps", {
        "session_key": session_key,
        "driver_number": driver_number,
    })
    return [{
        "lap_number":   l["lap_number"],
        "lap_duration": _lap_duration(l),
        "s1":           l.get("duration_sector_1"),
        "s2":           l.get("duration_sector_2"),
        "s3":           l.get("duration_sector_3"),
        "i1_speed":     l.get("i1_speed"),
        "i2_speed":     l.get("i2_speed"),
        "st_speed":     l.get("st_speed"),
        "is_pit_out":   l.get("is_pit_out_lap", False),
    } for l in laps]


# ─── STINTS ───────────────────────────────────────────────────────────────────

@app.get("/api/stints/{session_key}")
def get_stints(session_key: int, driver_number: Optional[int] = Query(None)):
    """Fetch tyre stint data. Optionally filter by driver."""
    params = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    stints = _openf1("stints", params)

    # Group by driver number
    grouped = {}
    for s in stints:
        dn = s["driver_number"]
        if dn not in grouped:
            grouped[dn] = []
        grouped[dn].append({
            "stint_number": s["stint_number"],
            "compound":     s.get("compound", "UNKNOWN"),
            "lap_start":    s["lap_start"],
            "lap_end":      s["lap_end"],
            "laps":         s["lap_end"] - s["lap_start"] + 1,
            "tyre_age_at_start": s.get("tyre_age_at_start", 0),
        })

    return grouped


# ─── RESULT ───────────────────────────────────────────────────────────────────

@app.get("/api/result/{session_key}")
def get_result(session_key: int):
    """Fetch session finishing order with driver info."""
    try:
        results = _openf1("session_result", {"session_key": session_key})
    except Exception:
        results = []

    if not results:
        return []

    # Enrich with driver info
    try:
        drivers = _openf1("drivers", {"session_key": session_key})
        driver_map = {d["driver_number"]: d for d in drivers}
    except Exception:
        driver_map = {}

    for r in results:
        d = driver_map.get(r["driver_number"], {})
        r["full_name"] = d.get("full_name", f"Driver {r['driver_number']}")
        r["name_acronym"] = d.get("name_acronym", "")
        r["team_name"] = d.get("team_name", "Unknown")
        r["team_colour"] = d.get("team_colour", "5a5a80")
    return sorted(results, key=lambda x: x.get("position") or 99)


# ─── STARTING GRID ────────────────────────────────────────────────────────────

@app.get("/api/starting_grid/{session_key}")
def get_starting_grid(session_key: int):
    """Fetch the starting grid for a race session."""
    grid = _openf1("starting_grid", {"session_key": session_key})
    return sorted(grid, key=lambda x: x.get("position") or 99)


# ─── WEATHER ──────────────────────────────────────────────────────────────────

@app.get("/api/weather/{session_key}")
def get_weather(session_key: int):
    """Fetch weather data for a session (first + last readings)."""
    weather = _openf1("weather", {"session_key": session_key})
    if not weather:
        return {"air_temperature": None, "track_temperature": None,
                "humidity": None, "wind_speed": None, "rainfall": False}

    # Return summary: averages of first and last reading
    first = weather[0]
    last = weather[-1]
    return {
        "air_temperature":   round((first.get("air_temperature", 0) + last.get("air_temperature", 0)) / 2, 1),
        "track_temperature": round((first.get("track_temperature", 0) + last.get("track_temperature", 0)) / 2, 1),
        "humidity":          round((first.get("humidity", 0) + last.get("humidity", 0)) / 2, 1),
        "wind_speed":        round((first.get("wind_speed", 0) + last.get("wind_speed", 0)) / 2, 1),
        "rainfall":          any(w.get("rainfall", 0) for w in weather),
        "n_readings":        len(weather),
    }


# ─── PREDICT ──────────────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    session_key: Optional[int] = None   # Qualifying session key (may be None for pre-quali)
    race_session_key: Optional[int] = None
    meeting_key: int
    circuit: str = "Australia"
    n_sims: int = 100000
    force_refresh: bool = False
    # How to choose the data source for building the grid:
    # "auto"          → current behaviour (qualifying if available, else sprint quali / practice / team rankings)
    # "full_quali"    → force main Qualifying session
    # "sprint_quali"  → force Sprint Qualifying / Sprint Shootout
    # "fp_only"       → ignore qualifying and sprint quali, estimate from practice / team rankings
    source_mode: str = "auto"


@app.post("/api/predict")
def predict(req: PredictRequest):
    """
    Run Monte Carlo prediction pipeline.
    Works with or without qualifying data:
    - If qualifying completed → use actual quali results
    - If only practice/sprint quali → estimate grid from best available data
    - If no session data → use driver list with team-based estimates
    """
    # Gather all sessions for this meeting
    try:
        sessions = _openf1("sessions", {"meeting_key": req.meeting_key})
    except Exception:
        sessions = []

    # Get driver info from ANY completed session
    driver_map = {}
    for s in sessions:
        if s.get("status") == "completed" or s.get("session_key") == req.session_key:
            try:
                drivers = _openf1("drivers", {"session_key": s["session_key"]})
                for d in drivers:
                    driver_map[d["driver_number"]] = d
                if driver_map:
                    break
            except Exception:
                pass

    # If still no drivers, try the race session or any session
    if not driver_map:
        for s in sessions:
            try:
                drivers = _openf1("drivers", {"session_key": s["session_key"]})
                for d in drivers:
                    driver_map[d["driver_number"]] = d
                if driver_map:
                    break
            except Exception:
                pass

    # Apply dynamic circuit SC/VSC/rain probabilities from OpenF1 when available
    try:
        circuit_key = None
        for s in sessions:
            if s.get("circuit_key"):
                circuit_key = s["circuit_key"]
                break
        if circuit_key is not None:
            dynamic_stats = _get_circuit_stats_from_openf1(circuit_key)
            if dynamic_stats:
                # Blend historical stats with prior and avoid hard 0%/100% extremes
                base = mc.CIRCUIT_PARAMS.get(req.circuit, mc.CIRCUIT_PARAMS.get("Australia", {})).copy()
                prior_sc = base.get("sc_prob", 0.5)
                prior_vsc = base.get("vsc_prob", 0.25)
                prior_rain = base.get("rain_prob", 0.15)
                emp_sc = float(dynamic_stats.get("sc_prob", prior_sc))
                emp_vsc = float(dynamic_stats.get("vsc_prob", prior_vsc))
                emp_rain = float(dynamic_stats.get("rain_prob", prior_rain))
                blend = 0.5  # 50% prior, 50% empirical

                def _blend(prior: float, empirical: float, floor: float = 0.05, ceil: float = 0.95) -> float:
                    v = prior * (1.0 - blend) + empirical * blend
                    return max(floor, min(ceil, v))

                base.update({
                    "sc_prob": _blend(prior_sc, emp_sc, floor=0.05),
                    "vsc_prob": _blend(prior_vsc, emp_vsc, floor=0.02),
                    "rain_prob": _blend(prior_rain, emp_rain, floor=0.01),
                })
                mc.CIRCUIT_PARAMS[req.circuit] = base
    except Exception:
        pass

    # Strategy: try data sources in order of quality
    qualifying = []
    prediction_basis = "estimated"
    source_mode = getattr(req, "source_mode", "auto") or "auto"

    # 1) Try actual qualifying results, depending on source_mode
    target_session_key: Optional[int] = None
    target_label = None

    if source_mode == "full_quali":
        q_sess = next(
            (s for s in sessions if s["session_name"] == "Qualifying" and s.get("status") == "completed"),
            None,
        )
        if q_sess:
            target_session_key = q_sess["session_key"]
            target_label = "Qualifying"
    elif source_mode == "sprint_quali":
        q_sess = next(
            (
                s for s in sessions
                if s["session_name"] in ("Sprint Qualifying", "Sprint Shootout") and s.get("status") == "completed"
            ),
            None,
        )
        if q_sess:
            target_session_key = q_sess["session_key"]
            target_label = q_sess["session_name"]
    elif source_mode == "auto" and req.session_key:
        target_session_key = req.session_key
        target_label = "Qualifying"

    if target_session_key:
        try:
            quali_results = _openf1("session_result", {"session_key": target_session_key})
            if quali_results:
                prediction_basis = (
                    "qualifying"
                    if source_mode == "auto"
                    else f"qualifying ({target_label or 'manual'})"
                )
                for r in sorted(quali_results, key=lambda x: x.get("position") or 99):
                    dn = r["driver_number"]
                    d = driver_map.get(dn, {})
                    pos = r.get("position", 22)
                    duration = r.get("duration")
                    q_time = None
                    if isinstance(duration, list):
                        for t in reversed(duration):
                            if t and t > 0:
                                q_time = t
                                break
                    elif duration and duration > 0:
                        q_time = duration
                    qualifying.append({
                        "pos":          pos,
                        "driver":       d.get("full_name", f"Driver {dn}"),
                        "team":         d.get("team_name", "Unknown"),
                        "q_time":       q_time,
                        "abbreviation": d.get("name_acronym", ""),
                        "driver_number": dn,
                        "team_colour":  d.get("team_colour", "5a5a80"),
                    })
        except Exception:
            pass

    # 2) If no quali data yet, try sprint qualifying or practice results
    if not qualifying:
        # Choose priority based on requested source_mode
        if source_mode == "fp_only":
            priority = ["Practice 3", "Practice 2", "Practice 1"]
        elif source_mode == "sprint_quali":
            priority = ["Sprint Qualifying", "Sprint Shootout"]
        elif source_mode == "full_quali":
            priority = ["Qualifying"]
        else:
            # auto
            priority = ["Sprint Qualifying", "Sprint Shootout", "Practice 3", "Practice 2", "Practice 1"]
        for pname in priority:
            target = next((s for s in sessions if s["session_name"] == pname and s.get("status") == "completed"), None)
            if not target:
                continue
            try:
                results = _openf1("session_result", {"session_key": target["session_key"]})
                if results:
                    prediction_basis = f"estimated ({pname})"
                    for r in sorted(results, key=lambda x: x.get("position") or 99):
                        dn = r["driver_number"]
                        d = driver_map.get(dn, {})
                        pos = r.get("position", 22)
                        duration = r.get("duration")
                        q_time = None
                        if isinstance(duration, (int, float)) and duration > 0:
                            q_time = duration
                        qualifying.append({
                            "pos":          pos,
                            "driver":       d.get("full_name", f"Driver {dn}"),
                            "team":         d.get("team_name", "Unknown"),
                            "q_time":       q_time,
                            "abbreviation": d.get("name_acronym", ""),
                            "driver_number": dn,
                            "team_colour":  d.get("team_colour", "5a5a80"),
                        })
                    break
            except Exception:
                continue

    # 3) Last resort: use driver list with team-based ordering
    if not qualifying and driver_map:
        prediction_basis = "estimated (team rankings)"
        # Rough 2026 team order for grid estimation
        team_rank = {
            "Mercedes": 1, "Ferrari": 2, "McLaren": 3, "Red Bull Racing": 4,
            "Aston Martin": 5, "Alpine": 6, "Williams": 7, "Racing Bulls": 8,
            "Haas F1 Team": 9, "Kick Sauber": 10, "Cadillac": 11, "Audi": 12,
        }
        sorted_drivers = sorted(
            driver_map.values(),
            key=lambda d: (team_rank.get(d.get("team_name", ""), 99), d.get("driver_number", 99))
        )
        for i, d in enumerate(sorted_drivers):
            qualifying.append({
                "pos":          i + 1,
                "driver":       d.get("full_name", f"Driver {d['driver_number']}"),
                "team":         d.get("team_name", "Unknown"),
                "q_time":       None,
                "abbreviation": d.get("name_acronym", ""),
                "driver_number": d["driver_number"],
                "team_colour":  d.get("team_colour", "5a5a80"),
            })

    if not qualifying:
        raise HTTPException(404, "No data available to generate predictions for this meeting.")

    # Fetch practice times (best lap per driver from FP sessions)
    fp_times = {}
    try:
        fp_sessions = [s for s in sessions if s.get("session_type") == "Practice" and s.get("status") == "completed"]
        for fps in fp_sessions:
            fp_key = fps["session_name"].lower().replace("practice ", "fp")
            fp_results = _openf1("session_result", {"session_key": fps["session_key"]})
            for fr in fp_results:
                dn = fr["driver_number"]
                d = driver_map.get(dn, {})
                name = d.get("full_name", f"Driver {dn}")
                if name not in fp_times:
                    fp_times[name] = {}
                dur = fr.get("duration")
                if isinstance(dur, (int, float)) and dur > 0:
                    fp_times[name][fp_key] = dur
    except Exception:
        pass

    # Build optional weekend_incidents with sprint performance for race prediction
    weekend_incidents: dict[str, dict] = {}
    try:
        sprint_session = next(
            (s for s in sessions if s.get("session_name") == "Sprint" and s.get("status") == "completed"),
            None,
        )
        if sprint_session:
            sprint_results = _openf1("session_result", {"session_key": sprint_session["session_key"]})
            if isinstance(sprint_results, list) and sprint_results:
                sprint_pos = {r["driver_number"]: r.get("position", 22) for r in sprint_results}
                qual_pos = {q["driver_number"]: q["pos"] for q in qualifying if q.get("driver_number") is not None}
                for q in qualifying:
                    dn = q.get("driver_number")
                    if not dn or dn not in sprint_pos or dn not in qual_pos:
                        continue
                    qpos = qual_pos[dn]
                    spos = sprint_pos[dn]
                    # Positive delta means gained positions vs grid in Sprint
                    delta = qpos - spos
                    # Normalise: base 0.5, ±0.05 per position change, clipped to [0,1]
                    sprint_perf = max(0.0, min(1.0, 0.5 + 0.05 * delta))
                    name = q["driver"]
                    weekend_incidents.setdefault(name, {})["sprint_perf"] = sprint_perf
    except Exception:
        weekend_incidents = {}

    # Run model pipeline
    result = mc.run_prediction_pipeline(
        qualifying=qualifying,
        fp_times=fp_times,
        circuit=req.circuit,
        n_sims=req.n_sims,
        weekend_incidents=weekend_incidents,
    )

    output = {
        "session_key":      req.session_key,
        "meeting_key":      req.meeting_key,
        "circuit":          req.circuit,
        "n_sims":           req.n_sims,
        "prediction_basis": prediction_basis,
        **result,
        "cached":           False,
    }
    return output


# ─── LOCATION (raw track outline) ────────────────────────────────────────────

@app.get("/api/track/{session_key}/{driver_number}")
def get_track_outline(session_key: int, driver_number: int):
    """
    Fetch one lap's worth of location data to build a track outline.
    Uses the first lap's data.
    """
    try:
        laps_data = _openf1("laps", {
            "session_key": session_key,
            "driver_number": driver_number,
        })
        valid_laps = [l for l in laps_data
                      if l.get("lap_duration") and l["lap_duration"] > 0
                      and not l.get("is_pit_out_lap")]
        if not valid_laps:
            return {"x": [], "y": [], "n_points": 0}

        target = valid_laps[0]
        lap_start = target.get("date_start")
        if not lap_start:
            return {"x": [], "y": [], "n_points": 0}

        from datetime import timedelta
        start_dt = datetime.fromisoformat(lap_start)
        end_dt = start_dt + timedelta(seconds=target.get("lap_duration", 90) + 1)

        location = _openf1("location", {
            "session_key": session_key,
            "driver_number": driver_number,
            "date>": lap_start,
            "date<": end_dt.isoformat(),
        })

        if not location:
            return {"x": [], "y": [], "n_points": 0}

        x_raw = [d["x"] for d in location]
        y_raw = [d["y"] for d in location]

        # Normalize
        x_min, x_max = min(x_raw), max(x_raw)
        y_min, y_max = min(y_raw), max(y_raw)
        x_range = x_max - x_min or 1
        y_range = y_max - y_min or 1

        return {
            "x": [round((v - x_min) / x_range, 4) for v in x_raw],
            "y": [round((v - y_min) / y_range, 4) for v in y_raw],
            "n_points": len(x_raw),
        }
    except Exception as e:
        raise HTTPException(502, f"Track outline fetch failed: {e}")
