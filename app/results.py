"""The results hub: every evaluation the project has, in one common shape.

Three sources, each against its own reference:
    simulated    the live simulator's scenario sweep; reference = the exact
                 simulated heart rate (app/static/lab/scenarios.json)
    ubfc         UBFC-rPPG recordings; reference = a contact pulse oximeter
                 recorded in sync with the video (results/real_fusion_ubfc.json,
                 written by scripts/eval_real_fusion.py)
    volunteers   real volunteers from the Collect screen; reference = a
                 smartwatch reading per 20 s window (collect.study())

The page only displays what this module returns, so the numbers on screen
come from the same Python that wrote them.
"""

from __future__ import annotations

import json
from pathlib import Path

import collect

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("green", "chrom", "pos", "trace")


def _row(label, n, mae, within5=None, selected=None, extra=None) -> dict:
    return {"label": label, "n": n, "mae": mae, "within5": within5, "selected": selected, **(extra or {})}


def simulated() -> dict:
    p = ROOT / "app" / "static" / "lab" / "scenarios.json"
    if not p.exists():
        return {"available": False, "how_to": "Run scripts/sim_scenarios.py to measure the simulated scenarios."}
    s = json.loads(p.read_text())
    o = s["overall"]
    by_skin = {}
    for sc in s["scenarios"]:
        for fz, a in sc["by_skin"].items():
            acc = by_skin.setdefault(fz, {"n": 0, **{m: 0.0 for m in METHODS}, "w5": 0.0})
            acc["n"] += a["n"]
            for m in METHODS:
                acc[m] += a["mae"][m] * a["n"]
            acc["w5"] += a["within5"]["trace"] * a["n"]
    skin_rows = [_row(f"Type {'I II III IV V VI'.split()[int(k) - 1]}", v["n"], {m: v[m] / v["n"] for m in METHODS},
                      {"trace": v["w5"] / v["n"]}) for k, v in sorted(by_skin.items(), key=lambda kv: int(kv[0]))]
    return {
        "available": True, "reference": "true simulated heart rate",
        "subjects": s["seeds"] * 6 * len(s["scenarios"]), "readings": o["n"],
        "overall": {"mae": o["mae"], "within5": o["within5"], "confident": o["confident"],
                    "mae_confident": o["mae_confident"], "mae_flagged": o["mae_flagged"]},
        "note": s.get("note") or "Simulated faces: the skin physics is modelled.",
        "fusion": s.get("fusion", 2),
        "breakdowns": [{"title": "BY SKIN TYPE", "rows": skin_rows}],
        "scenarios": s["scenarios"], "seeds": s["seeds"], "seconds": s["seconds"],
    }


def ubfc() -> dict:
    import os
    p = Path(os.environ.get("TRACE_UBFC_RESULTS", str(ROOT / "results" / "real_fusion_ubfc.json")))
    if not p.exists():
        return {"available": False, "how_to": "Download UBFC-rPPG subjects (for example to D:/datasets/ubfc), then run: "
                                              ".venv/Scripts/python.exe scripts/eval_real_fusion.py --dataset D:/datasets/ubfc"}
    r = json.loads(p.read_text())
    o = r["overall"]

    def pick(a):  # the scorer calls TRACE v3 "v3"; v2 is kept for the record
        return {"green": a["green"]["mae"], "chrom": a["chrom"]["mae"], "pos": a["pos"]["mae"], "trace": a["v3"]["mae"]}

    rows = [_row(subj, a["n"], pick(a), {"trace": a["v3"]["within5"]}, a.get("mean_weights_v3"))
            for subj, a in sorted(r["subjects"].items(), key=lambda kv: int("".join(c for c in kv[0] if c.isdigit()) or 0))]
    c = o.get("v3_confident", {})
    return {
        "available": True, "reference": "contact pulse oximeter (CMS50E), synchronised",
        "subjects": len(r["subjects"]), "readings": o["n"],
        "overall": {"mae": pick(o), "within5": {m: o[k]["within5"] for m, k in zip(METHODS, ("green", "chrom", "pos", "v3"))},
                    "confident": c.get("share"), "mae_confident": c.get("mae"), "mae_flagged": o.get("v3_flagged_mae"),
                    "v2_mae": o["v2"]["mae"]},
        "note": "UBFC-rPPG, Bobbia et al. 2017. Mostly lighter skin, so it tests real faces, not the skin-tone range.",
        "breakdowns": [{"title": "BY SUBJECT", "rows": rows}],
    }


def volunteers() -> dict:
    s = collect.study()
    if not s["n_readings"]:
        return {"available": False, "how_to": "Record volunteers on the Collect screen, with smartwatch readings at 0:20, 0:40 and 1:00."}
    o = s["overall"]

    def rows(g, fmt=lambda k: k):
        return [_row(fmt(k), a["n"], a["mae"], a["within5"], a.get("mean_weights"), {"people": a["volunteers"]}) for k, a in g.items()]

    roman = "I II III IV V VI".split()
    return {
        "available": True, "reference": "smartwatch reading over the same 20 s",
        "subjects": s["n_volunteers_scored"], "readings": s["n_readings"],
        "overall": {"mae": o["mae"], "within5": o["within5"], "confident": o.get("confident"),
                    "mae_confident": o.get("mae_confident"), "mae_flagged": None},
        "note": "Real people. The watch and TRACE average differently, so a few BPM of difference is expected even when both are right.",
        "breakdowns": [
            {"title": "BY MOTION", "rows": rows(s["by_motion"])},
            {"title": "BY LIGHTING", "rows": rows(s["by_lighting"])},
            {"title": "BY SKIN TYPE", "rows": rows(s["by_skin"], lambda k: f"Type {roman[int(k) - 1]}" if k.isdigit() else k)},
            {"title": "BY AGE GROUP", "rows": rows(s["by_age"])},
        ],
    }


def everything() -> dict:
    out = {}
    for key, fn in (("simulated", simulated), ("ubfc", ubfc), ("volunteers", volunteers)):
        try:
            out[key] = fn()
        except Exception as exc:  # one broken source must not hide the others
            out[key] = {"available": False, "how_to": f"Could not read these results: {exc}"}
    return out
