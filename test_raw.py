import sys, json
sys.path.append("/Users/aakashbaskar/Downloads/APEX_project/apex_backend")
from model_core import compute_raw_score, compute_features_v4, softmax_scores

drivers = ["Kimi Antonelli", "George Russell", "Sergio Perez", "Gabriel Bortoleto"]
teams = ["Mercedes", "Mercedes", "Cadillac", "Audi"]
pos = [1, 2, 21, 22]

all_entries = [{"driver": d, "team": t, "pos": p, "q_time": None, "fp": {}} for d,t,p in zip(drivers, teams, pos)]
raw = []
for e in all_entries:
    f = compute_features_v4(e, all_entries, "Shanghai")
    r = compute_raw_score(f, e["team"])
    raw.append(r)
    print(f"Driver {e['driver']} ({e['team']}) P{e['pos']} -> score: {r}")

probs = softmax_scores(raw)
for e, p in zip(all_entries, probs):
    print(f"  {e['driver']} win prob: {p * 100:.2f}%")
