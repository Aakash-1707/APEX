import sys, json
sys.path.append("/Users/aakashbaskar/Downloads/APEX_project/apex_backend")
from model_core import simulate_race_v4

import numpy as np
np.random.seed(42)

teams = ["Mercedes", "Ferrari", "McLaren", "Red Bull Racing", "Cadillac", "Audi"]
base = [0.4, 0.3, 0.15, 0.1, 0.02, 0.02] 
preds = [{"driver": f"Driver {i}", "team": teams[i], "win_prob": base[i], "grid_pos": i+1} for i in range(len(teams))]

print("Test simulation:")
for i in range(5):
    res = simulate_race_v4(preds)
    print(res)
