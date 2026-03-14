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
res = simulate_race_v4(preds)
print("Winner:", res[0] if res else "None")
