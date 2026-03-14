# APEX — F1 Strategy Intelligence

Real-time F1 prediction dashboard. Pulls live data from FastF1, runs the
2026-regulation-aware Monte Carlo model, and displays results across four tabs:
Telemetry · Tyre Deg · Quali Prediction · Race Prediction.

---

## Folder structure

```
APEX_project/
├── apex_backend/
│   ├── api.py            ← FastAPI server (all endpoints)
│   ├── model_core.py     ← Feature engineering + Monte Carlo model
│   ├── f1_loader.py      ← FastF1 data fetching + normalisation
│   └── requirements.txt  ← Python deps
├── src/
│   ├── App.jsx           ← React app (all UI)
│   └── main.jsx          ← React entry point
├── index.html
├── vite.config.js
├── package.json
└── README.md
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+

---

## First-time setup

### 1. Python backend

```bash
cd apex_backend
pip install -r requirements.txt
```

### 2. Node frontend

```bash
cd ..          # back to project root
npm install
```

---

## Running

You need **two terminals open at the same time**.

**Terminal 1 — Python API (port 8000)**
```bash
cd apex_backend
uvicorn api:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

**Terminal 2 — React frontend (port 3000)**
```bash
npm run dev
```

Then open **http://localhost:3000** in your browser.

---

## What happens on first use

1. Select a race weekend from the dropdown (R1 Australia opens by default)
2. The app calls `POST /api/predict` → FastF1 downloads qualifying + practice data
   from F1's timing servers — **first fetch takes 30–90 seconds**
3. Data is cached in `apex_backend/f1_cache/` — every reload after that is instant
4. The model runs 100,000 Monte Carlo simulations and returns predictions
5. Click **Telemetry** to see the animated track map with real GPS data
6. Click **Tyre Deg** to see actual stint data and lap time degradation
7. Click **Race Prediction** to see win%, podium%, DNF risk for all 22 drivers

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Server status + FastF1 availability |
| GET | /api/calendar | Full 2026 race calendar with mode flags |
| GET | /api/weekend/2026/{gp} | Session availability for a weekend |
| POST | /api/predict | Run full model pipeline |
| GET | /api/result/2026/{gp} | Actual race result (past races) |
| GET | /api/telemetry/2026/{gp}/{driver} | Car telemetry (300-point arrays) |
| GET | /api/stints/2026/{gp} | Tyre stint data |
| GET | /api/sectors/2026/{gp} | Sector times from qualifying |
| GET | /api/weather/2026/{gp} | Weather conditions |

Interactive API docs: **http://localhost:8000/docs**

---

## GP key names (use in API calls)

| Round | Name | gp key |
|-------|------|--------|
| R1 | Australian GP | `Australia` |
| R2 | Chinese GP | `China` |
| R3 | Japanese GP | `Japan` |
| R4 | Bahrain GP | `Bahrain` |
| R5 | Saudi Arabian GP | `Saudi Arabia` |
| R6 | Miami GP | `Miami` |
| ... | ... | ... |

---

## Troubleshooting

**Red "APEX BACKEND OFFLINE" banner**
→ Terminal 1 is not running. Start `uvicorn api:app --reload --port 8000`.

**"FastF1 not installed" error**
→ Run `pip install fastf1` inside `apex_backend/`.

**"Session not available" for a race**
→ FastF1 indexes data a few days after each race. 2026 Australian GP data
  should be available from ~March 17 2026 onwards.

**Predictions look wrong / want to re-run**
→ Pass `"force_refresh": true` in the POST body to bypass the cache.
  Or delete `apex_backend/prediction_cache/` and reload.

**CORS error in browser console**
→ Make sure you're opening http://localhost:3000 (not the Vite IP address).
  The Vite proxy in vite.config.js handles /api → port 8000 automatically.
