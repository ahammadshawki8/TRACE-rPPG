"""T11: fill the poster, extended abstract and course report from results.

Every number in the three documents comes from a results file, never from a
hand-typed value (CLAUDE.md Rule 1.3.5). Sentences whose wording depends on
the outcome (does the gap widen, does TRACE help) are composed here from the
data, so rerunning after real data rewrites them correctly.

    .venv/Scripts/python.exe scripts/build_deliverables.py [--tag sim] [--pdf]

Outputs:
    deliverables/poster/poster.html      (+ poster.pdf with --pdf, A1 portrait)
    deliverables/report/report.html      (+ report.pdf with --pdf, A4)
    deliverables/abstract/abstract.tex   IEEE conference format, for Overleaf
    deliverables/abstract/abstract.html  (+ abstract.pdf with --pdf)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DELIV = ROOT / "deliverables"
CHROME = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
          Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]

LABEL = {"green": "Green", "ica": "ICA", "chrom": "CHROM", "pos": "POS", "trace": "TRACE", "trace_v1": "TRACE v1",
         "trace_v2": "TRACE v2", "pos_mask": "POS + artifact mask", "pos_wiener": "POS + Wiener mask",
         "physnet": "PhysNet", "factorizephys": "FactorizePhys"}


def f1(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.1f}"


def f2(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.2f}"


def pval(p) -> str:
    if p is None or pd.isna(p):
        return "n/a"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def load(tag: str) -> dict:
    R = ROOT / "results"
    cells = pd.read_csv(R / f"cells_{tag}.csv")
    inter = pd.read_csv(R / f"interaction_{tag}.csv")
    summ = json.loads((R / f"summary_{tag}.json").read_text())
    power = pd.read_csv(R / f"power_{tag}.csv") if (R / f"power_{tag}.csv").exists() else None
    fusion = json.loads((R / "fusion_ablation_sim.json").read_text())
    params = json.loads((R / "fusion_params.json").read_text())
    harness = json.loads((R / "harness_validation_sim.json").read_text()) if (R / "harness_validation_sim.json").exists() else None
    hrv = json.loads((R / "hrv_sim.json").read_text()) if (R / "hrv_sim.json").exists() else None
    grid = pd.read_csv(R / f"grid_{tag}.csv")
    grid["ok"] = ((grid["est_bpm"] - grid["ref_bpm"]).abs() <= 5.0).astype(float)
    grid["group"] = ["IV-VI" if f >= 4 else "I-III" for f in grid["fitzpatrick"]]
    return {"cells": cells, "inter": inter, "summary": summ, "power": power, "fusion": fusion, "params": params,
            "harness": harness, "hrv": hrv, "tag": tag, "grid": grid}


def success(d, method, cond, group):
    g = d["grid"]
    r = g[(g["method"] == method) & (g["condition"] == cond) & (g["group"] == group)]
    return float(r["ok"].mean()) if len(r) else None


def pct(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{100 * x:.0f}%"


def mae_all(d, method, cond):
    a, b = mae(d, method, cond, "I-III"), mae(d, method, cond, "IV-VI")
    return None if a is None or b is None else (a + b) / 2


def mae(d, method, cond, group):
    c = d["cells"]
    r = c[(c["method"] == method) & (c["condition"] == cond) & (c["group"] == group)]
    return float(r["mae"].iloc[0]) if len(r) else None


def gap(d, method, cond):
    a, b = mae(d, method, cond, "I-III"), mae(d, method, cond, "IV-VI")
    return None if a is None or b is None else b - a


def inter_row(d, method, codec="h264"):
    i = d["inter"]
    r = i[(i["method"] == method) & (i["codec"] == codec)]
    return r.iloc[0] if len(r) else None


def verdict(d, method="pos", codec="h264") -> str:
    r = inter_row(d, method, codec)
    if r is None:
        return "The interaction could not be estimated."
    g0, g1 = gap(d, method, "lossless_rgb"), gap(d, method, f"{codec}_100k")
    widening = r["ci_high"] < 0
    narrowing = r["ci_low"] > 0
    core = (f"For {LABEL[method]} under {codec.upper().replace('H26', 'H.26')}, the dark-minus-light error gap was "
            f"{f1(g0)} BPM on lossless video and {f1(g1)} BPM at 100 kbps. The interaction coefficient was "
            f"{f2(r['coef'])} BPM per doubling of bitrate (95% CI {f2(r['ci_low'])} to {f2(r['ci_high'])}, "
            f"{pval(r['p'])}; subject bootstrap {f2(r['boot_low'])} to {f2(r['boot_high'])}).")
    lo = f"{codec}_100k"
    s_l0, s_d0 = success(d, method, "lossless_rgb", "I-III"), success(d, method, "lossless_rgb", "IV-VI")
    s_l1, s_d1 = success(d, method, lo, "I-III"), success(d, method, lo, "IV-VI")
    plateau = (f" Windows within 5 BPM: {pct(s_l0)} lighter vs {pct(s_d0)} darker on lossless video, "
               f"{pct(s_l1)} vs {pct(s_d1)} at 100 kbps.")
    if widening:
        return core + " The gap widened significantly as bitrate fell: the curves fan apart." + plateau
    if narrowing:
        return (core + " The gap narrowed as bitrate fell, the opposite of the hypothesis." + plateau
                + " Darker skin was already near its failure plateau at every bitrate, and compression pulled"
                  " lighter skin down to meet it: the narrowing reflects convergence at failure, not a benefit"
                  " to darker skin.")
    return (core + " The interval includes zero: in this sample the curves do not fan apart detectably." + plateau)


def headline(d: dict) -> str:
    """One sentence for the top of every document, chosen by the data."""
    rows = [inter_row(d, m, "h264") for m in ("pos", "chrom")]
    rows = [r for r in rows if r is not None]
    if any(r["ci_high"] < 0 for r in rows):
        return "Compression widened the skin-tone gap: the error curves fan apart as bitrate falls."
    if any(r["ci_low"] > 0 for r in rows):
        return ("Compression did not widen the skin-tone gap. Darker skin was already near its failure plateau at "
                "every bitrate, and compression dragged lighter skin down to meet it.")
    return "Compression did not detectably change the skin-tone gap in this sample; the curves stay roughly parallel."


def mitigation(d: dict) -> str:
    """Which method is best on lossless and at 400 kbps, and what the mask alone does."""
    cands = [m for m in ("green", "ica", "chrom", "pos", "pos_mask", "trace_v1", "trace", "physnet", "factorizephys")
             if mae_all(d, m, "lossless_rgb") is not None]
    best_ll = min(cands, key=lambda m: mae_all(d, m, "lossless_rgb"))
    best_400 = min(cands, key=lambda m: mae_all(d, m, "h264_400k") if mae_all(d, m, "h264_400k") is not None else 1e9)
    s = (f"On the full grid the lowest error on lossless video came from {LABEL.get(best_ll, best_ll)} "
         f"({f1(mae_all(d, best_ll, 'lossless_rgb'))} BPM) and at 400 kbps from {LABEL.get(best_400, best_400)} "
         f"({f1(mae_all(d, best_400, 'h264_400k'))}). TRACE scored {f1(mae_all(d, 'trace', 'lossless_rgb'))} and "
         f"{f1(mae_all(d, 'trace', 'h264_400k'))}; POS {f1(mae_all(d, 'pos', 'lossless_rgb'))} and "
         f"{f1(mae_all(d, 'pos', 'h264_400k'))}; POS with the artifact mask alone "
         f"{f1(mae_all(d, 'pos_mask', 'lossless_rgb'))} and {f1(mae_all(d, 'pos_mask', 'h264_400k'))}; "
         f"FactorizePhys {f1(mae_all(d, 'factorizephys', 'lossless_rgb'))} and "
         f"{f1(mae_all(d, 'factorizephys', 'h264_400k'))}. TRACE's lossless skin-tone gap was "
         f"{f1(gap(d, 'trace', 'lossless_rgb'))} BPM against {f1(gap(d, 'pos', 'lossless_rgb'))} for POS.")
    return s


def fill(template: str, values: dict) -> str:
    def rep(m):
        key = m.group(1)
        if key not in values:
            raise KeyError(f"template placeholder {{{{{key}}}}} has no value")
        return str(values[key])
    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", rep, template)


def values(d: dict) -> dict:
    s, fu, p = d["summary"], d["fusion"], d["params"]
    sim = s["source"] == "simulated"
    v = {
        "SOURCE_NOTE": ("All results below come from a simulated pilot: real codecs, real detector and real pipeline "
                        "applied to rendered faces whose skin-tone physics is modelled. They test the mechanism, "
                        "not real people.") if sim else "Results from recorded participants.",
        "N_SUBJECTS": s["n_subjects"], "N_PER_GROUP": s["n_subjects"] // 2,
        "BITRATES": ", ".join(str(b) for b in s["bitrates"]),
        "CODECS": ", ".join(c.upper().replace("H26", "H.26") for c in s["codecs"]),
        "HEADLINE": headline(d), "MITIGATION": mitigation(d),
        "VERDICT_POS": verdict(d, "pos"), "VERDICT_CHROM": verdict(d, "chrom"),
        "VERDICT_TRACE": verdict(d, "trace"),
        "POS_LL_LIGHT": f1(mae(d, "pos", "lossless_rgb", "I-III")), "POS_LL_DARK": f1(mae(d, "pos", "lossless_rgb", "IV-VI")),
        "POS_100_LIGHT": f1(mae(d, "pos", "h264_100k", "I-III")), "POS_100_DARK": f1(mae(d, "pos", "h264_100k", "IV-VI")),
        "TRACE_LL_LIGHT": f1(mae(d, "trace", "lossless_rgb", "I-III")), "TRACE_LL_DARK": f1(mae(d, "trace", "lossless_rgb", "IV-VI")),
        "TRACE_100_LIGHT": f1(mae(d, "trace", "h264_100k", "I-III")), "TRACE_100_DARK": f1(mae(d, "trace", "h264_100k", "IV-VI")),
        "GAP_POS_LL": f1(gap(d, "pos", "lossless_rgb")), "GAP_POS_100": f1(gap(d, "pos", "h264_100k")),
        "GAP_TRACE_LL": f1(gap(d, "trace", "lossless_rgb")), "GAP_TRACE_100": f1(gap(d, "trace", "h264_100k")),
        "FUSION_POS": f1(fu.get("pos")), "FUSION_ICA": f1(fu.get("ica")),
        "FUSION_V1": f1(next((v for k, v in fu.items() if k.startswith("TRACE v1")), None)),
        "FUSION_V2": f1(next((v for k, v in fu.items() if k.startswith("TRACE v2 (gamma")), None)),
        "FUSION_MASK": f1(fu.get("POS + artifact mask (no fusion)")),
        "FUSION_CONF_MAE": f1(fu.get("confident_mae")), "FUSION_FLAG_MAE": f1(fu.get("flagged_mae")),
        "FUSION_COVERAGE": f"{100 * fu.get('coverage', 0):.0f}",
        "GAMMA": p["gamma"], "MASK_K": p["mask_k"], "CONF": f2(p["confidence"]),
        "GRID_POS_LL": f1(mae_all(d, "pos", "lossless_rgb")), "GRID_MASK_LL": f1(mae_all(d, "pos_mask", "lossless_rgb")),
        "GRID_TRACE_LL": f1(mae_all(d, "trace", "lossless_rgb")), "GRID_POS_400": f1(mae_all(d, "pos", "h264_400k")),
        "GRID_MASK_400": f1(mae_all(d, "pos_mask", "h264_400k")), "GRID_TRACE_400": f1(mae_all(d, "trace", "h264_400k")),
        "GRID_FP_LL": f1(mae_all(d, "factorizephys", "lossless_rgb")), "GRID_FP_400": f1(mae_all(d, "factorizephys", "h264_400k")),
        "GRID_TRACE_100": f1(mae_all(d, "trace", "h264_100k")), "GRID_FP_100": f1(mae_all(d, "factorizephys", "h264_100k")),
        "W5_POS_LL_LIGHT": pct(success(d, "pos", "lossless_rgb", "I-III")),
        "W5_POS_LL_DARK": pct(success(d, "pos", "lossless_rgb", "IV-VI")),
        "W5_POS_100_LIGHT": pct(success(d, "pos", "h264_100k", "I-III")),
        "W5_POS_100_DARK": pct(success(d, "pos", "h264_100k", "IV-VI")),
    }
    for m in ("physnet", "factorizephys"):
        key = m.upper()
        v[f"{key}_LL_LIGHT"] = f1(mae(d, m, "lossless_rgb", "I-III"))
        v[f"{key}_LL_DARK"] = f1(mae(d, m, "lossless_rgb", "IV-VI"))
        v[f"{key}_100_LIGHT"] = f1(mae(d, m, "h264_100k", "I-III"))
        v[f"{key}_100_DARK"] = f1(mae(d, m, "h264_100k", "IV-VI"))
        v[f"VERDICT_{key}"] = verdict(d, m)
    h = d["harness"]
    keys = {"FID_LL": "lossless_rgb", "FID_420": "lossless_yuv420", "FID_1600": "h264_1600k",
            "FID_400": "h264_400k", "FID_100": "h264_100k", "FID_H265_100": "h265_100k", "FID_VP9_100": "vp9_100k"}
    for k, cond in keys.items():
        for skin in ("II", "VI"):
            try:
                v[f"{k}_{skin}"] = f2(h["pulse_fidelity"][cond][skin])
            except (TypeError, KeyError):
                v[f"{k}_{skin}"] = "n/a"
    pw = d["power"]
    if pw is not None:
        eff = sorted(pw["effect_bpm_per_doubling"].unique())
        target = 1.0 if 1.0 in eff else eff[len(eff) // 2]
        rows = pw[(pw["effect_bpm_per_doubling"] == target) & (pw["power"] >= 0.8)]
        v["POWER_EFFECT"] = f1(target)
        v["POWER_N"] = f"about {int(rows['n_per_group'].min())}" if len(rows) else "more than 40"
    else:
        v["POWER_EFFECT"], v["POWER_N"] = "n/a", "n/a"
    hr = d["hrv"]
    if hr and "natural_sdnn_mae" in hr:
        v["HRV_SDNN_MAE"], v["HRV_RMSSD_MAE"] = f1(hr["natural_sdnn_mae"]), f1(hr["natural_rmssd_mae"])
        v["HRV_CLEAN_SDNN"], v["HRV_CLEAN_RMSSD"] = f1(hr["clean_sdnn_mae"]), f1(hr["clean_rmssd_mae"])
    else:
        v["HRV_SDNN_MAE"] = v["HRV_RMSSD_MAE"] = v["HRV_CLEAN_SDNN"] = v["HRV_CLEAN_RMSSD"] = "n/a"
    return v


def to_pdf(html: Path, pdf: Path) -> bool:
    exe = next((c for c in CHROME if c.exists()), None)
    if exe is None:
        return False
    subprocess.run([str(exe), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=8000",
                    f"--print-to-pdf={pdf}", html.as_uri()], check=True, capture_output=True, timeout=180)
    return pdf.exists()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sim")
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args()
    d = load(args.tag)
    v = values(d)
    figs = ROOT / "results" / "figures"
    for doc, name in (("poster", "poster.html"), ("report", "report.html"), ("abstract", "abstract.html"),
                      ("abstract", "abstract.tex")):
        tpl = DELIV / doc / f"template_{name}"
        out = DELIV / doc / name
        vals = v
        if name.endswith(".tex"):
            # Values are plain text; LaTeX treats % as a comment and _ & # as special.
            esc = {"%": r"\%", "&": r"\&", "_": r"\_", "#": r"\#"}
            vals = {k: "".join(esc.get(ch, ch) for ch in str(x)) for k, x in v.items()}
        out.write_text(fill(tpl.read_text(encoding="utf-8"), vals), encoding="utf-8")
        fig_dir = DELIV / doc / "figures"
        fig_dir.mkdir(exist_ok=True)
        for f in figs.glob(f"{args.tag}_*.png"):
            shutil.copy(f, fig_dir / f.name.replace(f"{args.tag}_", ""))
        if (figs / "sim_mechanism.png").exists():
            shutil.copy(figs / "sim_mechanism.png", fig_dir / "mechanism.png")
        print(f"  wrote {out.relative_to(ROOT)}")
        if args.pdf and name.endswith(".html"):
            ok = to_pdf(out, out.with_suffix(".pdf"))
            print(f"  {'wrote' if ok else 'could not write'} {out.with_suffix('.pdf').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
