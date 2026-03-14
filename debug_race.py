import sys, json, math
sys.path.append("/Users/aakashbaskar/Downloads/APEX_project/apex_backend")
from model_core import simulate_race_v4
import numpy as np

teams = [
    "Mercedes", "Mercedes", "Ferrari", "Ferrari", "McLaren", "McLaren",
    "Red Bull Racing", "Red Bull Racing", "Aston Martin", "Aston Martin",
    "Alpine", "Alpine", "Williams", "Williams", "Racing Bulls", "Racing Bulls",
    "Haas F1 Team", "Haas F1 Team", "Kick Sauber", "Kick Sauber", "Cadillac", "Audi"
]
base = [
    0.35, 0.35, 0.10, 0.10, 0.05, 0.05, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
]
preds = [{"driver": f"Driver {i}", "team": teams[i], "win_prob": base[i], "grid_pos": i+1} for i in range(len(teams))]

np.random.seed(189)
circuit_p = {"sc_prob": 0.50, "vsc_prob": 0.22, "rain_prob": 0.10, "pole_win_rate": 0.48}
base_arr = np.array([p["win_prob"] for p in preds], dtype=float)
noise_scale = base_arr * 0.35 + 0.015
performance = np.random.normal(base_arr, noise_scale)

print(f"Base performance: {performance}")
leader_val = performance.max()
compression = 0.3
if np.random.random() < circuit_p["sc_prob"]:
    performance = performance * (1 - compression) + leader_val * compression
    performance += np.random.normal(0, 0.02, len(teams))
print(f"After SC: {performance}")

if np.random.random() < circuit_p["vsc_prob"]:
    performance *= 0.9
    performance += np.random.uniform(0, 0.08, len(teams))
print(f"After VSC: {performance}")

if np.random.random() < circuit_p["rain_prob"]:
    performance += np.random.normal(0, 0.04, len(teams))
print(f"After Rain: {performance}")

if np.random.random() < 0.35: # lap 1 incident
    n_victims = np.random.choice([1, 2, 3], p=[0.5, 0.35, 0.15])
    for _ in range(n_victims):
        victim = np.random.randint(2, min(14, len(teams)))
        performance[victim] *= np.random.uniform(0.15, 0.55)
print(f"After lap 1 incident: {performance}")

for i, p in enumerate(preds):
    gp = p["grid_pos"]
    if gp > 5:
        overtake_boost = (gp - 5) * 0.0001 * 1.4 * base_arr[i]
        performance[i] += overtake_boost * np.random.uniform(0.3, 1.0)
print(f"After Overtake Boost: {performance}")

for i in range(1, len(teams)):
    if np.random.random() < 0.15:
        performance[i] += 0.02

for i, team in enumerate(teams):
    if np.random.random() < 0.08:
        performance[i] = -1

for i in range(len(teams)):
    if np.random.random() < 0.04:
        performance[i] *= np.random.uniform(0.2, 0.6)

performance += np.random.normal(0, 0.012, len(teams))
print(f"Final performance: {performance}")
