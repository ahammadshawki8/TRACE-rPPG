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


def _tv(a: dict) -> str:  # the newest TRACE version the scorer wrote; older ones are kept for the record
    return "v4" if "v4" in a else "v3"


def _pick(a: dict) -> dict:
    return {"green": a["green"]["mae"], "chrom": a["chrom"]["mae"], "pos": a["pos"]["mae"], "trace": a[_tv(a)]["mae"]}


def _real(p: Path, reference: str, note: str) -> dict:
    """One contact-referenced dataset scored by scripts/eval_real_fusion.py."""
    r = json.loads(p.read_text())
    o = r["overall"]
    rows = [_row(subj, a["n"], _pick(a), {"trace": a[_tv(a)]["within5"]}, a.get("mean_weights_v3"))
            for subj, a in sorted(r["subjects"].items(), key=lambda kv: int("".join(c for c in kv[0] if c.isdigit()) or 0))]
    c = o.get(f"{_tv(o)}_confident", {})
    return {
        "available": True, "reference": reference,
        "subjects": len(r["subjects"]), "readings": o["n"],
        "overall": {"mae": _pick(o), "within5": {m: o[k]["within5"] for m, k in zip(METHODS, ("green", "chrom", "pos", _tv(o)))},
                    "confident": c.get("share"), "mae_confident": c.get("mae"), "mae_flagged": o.get(f"{_tv(o)}_flagged_mae"),
                    "v2_mae": o["v2"]["mae"]},
        "note": note,
        "breakdowns": [{"title": "BY SUBJECT", "rows": rows}],
        "_raw": r,
    }


def ubfc() -> dict:
    import os
    p = Path(os.environ.get("TRACE_UBFC_RESULTS", str(ROOT / "results" / "real_fusion_ubfc.json")))
    if not p.exists():
        return {"available": False, "how_to": "Download UBFC-rPPG subjects (scripts/download_ubfc.py), then run: "
                                              ".venv/Scripts/python.exe scripts/eval_real_fusion.py --dataset D:/datasets/ubfc"}
    out = _real(p, "contact pulse oximeter (CMS50E), synchronised",
                "UBFC-rPPG, Bobbia et al. 2017. People sit still in good light, and most have lighter skin: "
                "it tests real faces, not motion or the skin-tone range. TRACE v4 was tuned on these 22 subjects "
                "(with simulated faces), so this tab shows fit, not proof; the volunteers are the held-out test.")
    out.pop("_raw")
    return out


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


def learned() -> dict:
    """Classical against learned, on exactly the same volunteer watch readings.

    Option 1: two pretrained neural networks (rPPG-Toolbox, trained on PURE)
    read the saved volunteer videos (scripts/nn_volunteers.py). Option 2: a
    small learned selector picks green, CHROM or POS per window, trained only
    on UBFC-rPPG and simulated data (scripts/ml_select.py). The oracle is the
    ceiling: it looks at the watch, so it is not a method. None of these ever
    changes a number TRACE reports.
    """
    res = ROOT / "results"
    ml_p, nn_p = res / "ml_volunteers.json", res / "nn_volunteers.json"
    if not ml_p.exists():
        return {"available": False}
    ml = json.loads(ml_p.read_text())
    nn = json.loads(nn_p.read_text()) if nn_p.exists() else None
    rows = [
        {"key": "green", "label": "Green", "kind": "classical", "note": "one colour channel"},
        {"key": "chrom", "label": "CHROM", "kind": "classical", "note": "colour differences"},
        {"key": "pos", "label": "POS", "kind": "classical", "note": "the baseline to beat"},
        {"key": "trace", "label": "TRACE", "kind": "trace", "note": "picks the sharpest method each window"},
        {"key": "ml", "label": "TRACE + ML selector", "kind": "learned",
         "note": "gradient-boosted trees choose the method; trained on UBFC and simulation only"},
    ]
    for r in rows:
        r["mae"], r["within5"] = ml["mae"][r["key"]], ml["within5"][r["key"]]
    if nn and nn.get("n_readings") == ml["n_readings"]:
        for key, label in (("factorizephys", "FactorizePhys (neural)"), ("physnet", "PhysNet (neural)")):
            rows.append({"key": key, "label": label, "kind": "neural", "mae": nn["mae"][key], "within5": nn["within5"][key],
                         "note": "pretrained deep network, reads the face video; trained on PURE"})
    rows.append({"key": "oracle", "label": "Oracle (ceiling)", "kind": "ceiling", "mae": ml["mae"]["oracle"],
                 "within5": ml["within5"]["oracle"], "note": "the best of the three per window, chosen by looking at the watch"})
    return {"available": True, "n_people": ml["n_people"], "n_readings": ml["n_readings"], "rows": rows,
            "trace_version": ml.get("trace_version")}


def everything() -> dict:
    out = {}
    for key, fn in (("simulated", simulated), ("ubfc", ubfc), ("volunteers", volunteers), ("learned", learned)):
        try:
            out[key] = fn()
        except Exception as exc:  # one broken source must not hide the others
            out[key] = {"available": False, "how_to": f"Could not read these results: {exc}"}
    return out
