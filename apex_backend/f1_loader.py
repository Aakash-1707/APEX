"""
APEX FastF1 Loader
==================
Pulls real session data from FastF1 and normalises it into the format
expected by model_core.run_prediction_pipeline().

For upcoming races (no qualifying data yet) it falls back to FP data only,
applying a larger uncertainty penalty in the model.
"""

import os
import warnings
import numpy as np
from typing import Optional

try:
    import fastf1
    import fastf1.plotting
    FASTF1_AVAILABLE = True
except ImportError:
    FASTF1_AVAILABLE = False
    warnings.warn("FastF1 not installed. Run: pip install fastf1")

CACHE_DIR = os.path.join(os.path.dirname(__file__), "f1_cache")


def _setup_cache():
    if not FASTF1_AVAILABLE:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE_DIR)


def _load_session(year: int, gp: str, session_type: str):
    """Load and return a FastF1 session object."""
    if not FASTF1_AVAILABLE:
        raise ImportError("FastF1 not installed")
    _setup_cache()
    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=False, weather=True, messages=True)
    return session


# ─── QUALIFYING ───────────────────────────────────────────────────────────────

def fetch_qualifying(year: int, gp: str) -> list[dict]:
    """
    Returns list of:
        {pos, driver, team, q_time (seconds or None), abbreviation}
    Sorted by grid position.
    """
    session = _load_session(year, gp, "Q")
    results = session.results
    grid = []

    for _, row in results.iterrows():
        q_time = None
        for q_col in ["Q3", "Q2", "Q1"]:
            val = row.get(q_col)
            if val is not None:
                try:
                    t = val.total_seconds()
                    if t > 0:
                        q_time = t
                        break
                except (AttributeError, TypeError):
                    continue

        pos = int(row["Position"]) if not np.isnan(row.get("Position", float("nan"))) else 22
        grid.append({
            "pos":          pos,
            "driver":       row["FullName"],
            "team":         row["TeamName"],
            "q_time":       q_time,
            "abbreviation": row["Abbreviation"],
        })

    grid.sort(key=lambda x: x["pos"])
    return grid


# ─── PRACTICE TIMES ───────────────────────────────────────────────────────────

def fetch_fp_times(year: int, gp: str, available_sessions: list[str] = None) -> dict:
    """
    Returns {driver_full_name: {fp1, fp2, fp3}} with actual lap times in seconds.
    Missing sessions are filled with a large penalty value.

    available_sessions: list of session names to try, e.g. ["FP1","FP2","FP3"]
                        If None, tries all three.
    """
    sessions_to_try = available_sessions or ["FP1", "FP2", "FP3"]
    times = {}  # driver → {fp1, fp2, fp3}

    for fp_label in sessions_to_try:
        fp_num = fp_label.lower().replace("fp", "")
        key = f"fp{fp_num}"
        try:
            session = _load_session(year, gp, fp_label)
            laps = session.laps

            # Get fastest VALID lap per driver (no in/out laps, no SC laps)
            clean = laps[laps["IsAccurate"] == True] if "IsAccurate" in laps.columns else laps

            for driver_abbr in clean["Driver"].unique():
                driver_laps = clean[clean["Driver"] == driver_abbr]
                if driver_laps.empty:
                    continue
                best = driver_laps["LapTime"].min()
                try:
                    lap_s = best.total_seconds()
                except AttributeError:
                    continue

                try:
                    info = session.get_driver(driver_abbr)
                    full_name = f"{info['FirstName']} {info['LastName']}"
                except Exception:
                    full_name = driver_abbr

                if full_name not in times:
                    times[full_name] = {}
                times[full_name][key] = round(lap_s, 3)

        except Exception as e:
            warnings.warn(f"Could not load {fp_label} for {gp} {year}: {e}")

    # Fill missing sessions with penalty
    all_drivers = set(times.keys())
    for driver in all_drivers:
        for fp_key in ["fp1", "fp2", "fp3"]:
            if fp_key not in times[driver]:
                # Use the worst time in the available session + 2s penalty
                available_times = [
                    times[d].get(fp_key, None)
                    for d in all_drivers
                    if times[d].get(fp_key) is not None
                ]
                worst = max(available_times) + 2.0 if available_times else 85.0
                times[driver][fp_key] = worst

    return times


# ─── RACE RESULTS ─────────────────────────────────────────────────────────────

def fetch_race_result(year: int, gp: str, session_type: str = "R") -> list[dict]:
    """
    Fetch actual race finishing order.

    Returns list of:
        {pos, driver, team, grid, status, gap, points}
    """
    session = _load_session(year, gp, session_type)
    results = session.results
    output = []

    for _, row in results.iterrows():
        pos_val = row.get("Position")
        try:
            pos = int(pos_val) if pos_val and not np.isnan(float(pos_val)) else None
        except (ValueError, TypeError):
            pos = None

        status = str(row.get("Status", ""))
        output.append({
            "pos":    pos,
            "driver": row["FullName"],
            "team":   row["TeamName"],
            "grid":   int(row.get("GridPosition", 0)) if row.get("GridPosition") else 0,
            "status": status,
            "gap":    str(row.get("Time", "")),
            "points": float(row.get("Points", 0)),
        })

    output.sort(key=lambda x: (x["pos"] is None, x["pos"] or 99))
    return output


# ─── TELEMETRY ────────────────────────────────────────────────────────────────

def fetch_telemetry(
    year: int, gp: str,
    driver_abbr: str,
    session_type: str = "R",
    lap_number: Optional[int] = None,
) -> dict:
    """
    Fetch car telemetry for a specific driver.

    Returns dict with arrays:
        distance, x, y, speed, throttle, brake, gear, drs, n_points
    All arrays are same length and sampled at ~3.7Hz (FastF1 default).

    If lap_number is None, returns the driver's fastest lap.
    """
    _setup_cache()
    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=True, weather=False, messages=False)

    laps = session.laps.pick_driver(driver_abbr)
    if laps.empty:
        return _empty_telemetry()

    if lap_number is not None:
        lap = laps[laps["LapNumber"] == lap_number]
        if lap.empty:
            return _empty_telemetry()
        lap = lap.iloc[0]
    else:
        # Fastest valid lap
        valid = laps[laps["IsAccurate"] == True] if "IsAccurate" in laps.columns else laps
        if valid.empty:
            valid = laps
        lap = valid.loc[valid["LapTime"].idxmin()]

    tel = lap.get_car_data().add_distance()
    pos = lap.get_pos_data()

    # Resample to fixed 300 points for frontend consistency
    n_points = 300
    original_n = len(tel)
    if original_n < 2:
        return _empty_telemetry()

    indices = np.linspace(0, original_n - 1, n_points).astype(int)

    # Merge position data onto telemetry by time
    try:
        merged = tel.merge_channels(pos)
        x_raw = merged["X"].iloc[indices].tolist()
        y_raw = merged["Y"].iloc[indices].tolist()
    except Exception:
        x_raw = [0.0] * n_points
        y_raw = [0.0] * n_points

    # Normalise X/Y to 0-1 range for frontend SVG mapping
    x_arr = np.array(x_raw, dtype=float)
    y_arr = np.array(y_raw, dtype=float)
    x_min, x_max = x_arr.min(), x_arr.max()
    y_min, y_max = y_arr.min(), y_arr.max()
    x_norm = ((x_arr - x_min) / (x_max - x_min + 1e-9)).tolist()
    y_norm = ((y_arr - y_min) / (y_max - y_min + 1e-9)).tolist()

    # Core telemetry channels
    dist  = tel["Distance"].iloc[indices].tolist()
    speed = tel["Speed"].iloc[indices].fillna(0).astype(int).tolist()
    thr   = tel["Throttle"].iloc[indices].fillna(0).round(1).tolist()

    # Brake: FastF1 returns bool or 0/100
    brk_raw = tel["Brake"].iloc[indices]
    brk = (brk_raw.astype(float) * 100).round(1).tolist()

    gear  = tel["nGear"].iloc[indices].fillna(0).astype(int).tolist()
    drs_raw = tel["DRS"].iloc[indices] if "DRS" in tel.columns else [0]*n_points
    drs = [int(v) for v in drs_raw]

    # Lap time
    lap_time_s = None
    try:
        lap_time_s = lap["LapTime"].total_seconds()
    except Exception:
        pass

    return {
        "driver":    driver_abbr,
        "lap":       int(lap["LapNumber"]) if lap_number is None else lap_number,
        "lap_time":  round(lap_time_s, 3) if lap_time_s else None,
        "n_points":  n_points,
        "distance":  [round(d, 1) for d in dist],
        "x":         [round(v, 4) for v in x_norm],
        "y":         [round(v, 4) for v in y_norm],
        "speed":     speed,
        "throttle":  thr,
        "brake":     brk,
        "gear":      gear,
        "drs":       drs,
    }


def _empty_telemetry() -> dict:
    return {
        "driver": None, "lap": None, "lap_time": None, "n_points": 0,
        "distance": [], "x": [], "y": [], "speed": [], "throttle": [],
        "brake": [], "gear": [], "drs": [],
    }


# ─── STINT / TYRE DATA ────────────────────────────────────────────────────────

def fetch_stints(year: int, gp: str, session_type: str = "R") -> dict:
    """
    Fetch tyre stint data for all drivers.

    Returns {driver_full_name: [
        {compound, start_lap, end_lap, laps, lap_times: [float...]}
    ]}
    """
    _setup_cache()
    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=False, weather=False, messages=False)

    laps = session.laps
    stints = {}

    for driver_abbr in laps["Driver"].unique():
        try:
            info = session.get_driver(driver_abbr)
            full_name = f"{info['FirstName']} {info['LastName']}"
        except Exception:
            full_name = driver_abbr

        driver_laps = laps[laps["Driver"] == driver_abbr].copy()
        driver_laps = driver_laps.sort_values("LapNumber")

        driver_stints = []
        current_compound = None
        stint_start = None
        stint_times = []

        for _, lap_row in driver_laps.iterrows():
            compound = str(lap_row.get("Compound", "UNKNOWN")).upper()
            lap_num  = int(lap_row["LapNumber"])
            try:
                lt = lap_row["LapTime"].total_seconds()
            except Exception:
                lt = None

            if compound != current_compound:
                if current_compound is not None:
                    driver_stints.append({
                        "compound":  current_compound,
                        "start_lap": stint_start,
                        "end_lap":   lap_num - 1,
                        "laps":      lap_num - stint_start,
                        "lap_times": [t for t in stint_times if t is not None],
                    })
                current_compound = compound
                stint_start = lap_num
                stint_times = [lt] if lt else []
            else:
                if lt:
                    stint_times.append(lt)

        # Close the last stint
        if current_compound is not None:
            last_lap = int(driver_laps["LapNumber"].max())
            driver_stints.append({
                "compound":  current_compound,
                "start_lap": stint_start,
                "end_lap":   last_lap,
                "laps":      last_lap - stint_start + 1,
                "lap_times": [t for t in stint_times if t is not None],
            })

        stints[full_name] = driver_stints

    return stints


# ─── SECTOR TIMES ─────────────────────────────────────────────────────────────

def fetch_sector_times(year: int, gp: str, session_type: str = "Q") -> dict:
    """
    Returns {driver_full_name: {best_lap, s1, s2, s3, speed_trap}}
    """
    session = _load_session(year, gp, session_type)
    laps = session.laps
    result = {}

    for driver_abbr in laps["Driver"].unique():
        driver_laps = laps[laps["Driver"] == driver_abbr]
        if driver_laps.empty:
            continue

        best_row = driver_laps.loc[driver_laps["LapTime"].idxmin()] if not driver_laps.empty else None
        if best_row is None:
            continue

        try:
            info = session.get_driver(driver_abbr)
            full_name = f"{info['FirstName']} {info['LastName']}"
        except Exception:
            full_name = driver_abbr

        def to_sec(val):
            try:
                return round(val.total_seconds(), 3)
            except Exception:
                return None

        result[full_name] = {
            "best_lap":   to_sec(best_row.get("LapTime")),
            "s1":         to_sec(best_row.get("Sector1Time")),
            "s2":         to_sec(best_row.get("Sector2Time")),
            "s3":         to_sec(best_row.get("Sector3Time")),
            "speed_trap": float(best_row["SpeedST"]) if best_row.get("SpeedST") else None,
        }

    return result


# ─── WEATHER ──────────────────────────────────────────────────────────────────

def fetch_weather(year: int, gp: str, session_type: str = "R") -> dict:
    session = _load_session(year, gp, session_type)
    w = session.weather_data
    if w is None or w.empty:
        return {"air_temp": None, "track_temp": None, "humidity": None,
                "wind_speed": None, "rain": False}
    return {
        "air_temp":   round(float(w["AirTemp"].mean()), 1),
        "track_temp": round(float(w["TrackTemp"].mean()), 1),
        "humidity":   round(float(w["Humidity"].mean()), 1),
        "wind_speed": round(float(w["WindSpeed"].mean()), 1),
        "rain":       bool(w["Rainfall"].any()),
    }
