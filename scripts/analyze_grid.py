"""T7: statistics and figures from a grid CSV.

Reads results/grid_<tag>.csv and writes:
    results/cells_<tag>.csv            MAE and subject-bootstrap CI per cell
    results/interaction_<tag>.csv      the interaction model per method x codec
    results/summary_<tag>.json         headline numbers for the write-up
    results/power_<tag>.csv            power for real-data planning
    results/figures/<tag>_*.png        the figures

Colour: tone groups are blue (I to III) and crimson (IV to VI), validated
with the dataviz palette checker (CVD delta E 23.4, all checks pass), and
always paired with marker shape and a direct label so colour is never the
only cue. Every figure built from simulated data says so in its title.

Usage: .venv/Scripts/python.exe scripts/analyze_grid.py [--tag sim]
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from _common import ROOT  # noqa: E402
from tracerppg.metrics import bland_altman  # noqa: E402
from tracerppg.stats import cell_table, interaction, power_interaction, subject_condition_errors  # noqa: E402

INK, INK2, RULE, SURFACE = "#1F1720", "#5A4E58", "#E0D6DB", "#FCFCFB"
TONE = {"I-III": ("#2a78d6", "o", "Fitzpatrick I to III"), "IV-VI": ("#B01B3F", "s", "Fitzpatrick IV to VI")}
METHOD_LABEL = {"green": "Green", "ica": "ICA", "chrom": "CHROM", "pos": "POS", "trace": "TRACE",
                "trace_v1": "TRACE v1", "trace_v2": "TRACE v2", "trace_v3": "TRACE v3",
                "pos_mask": "POS + mask", "pos_wiener": "POS + Wiener",
                "physnet": "PhysNet", "factorizephys": "FactorizePhys"}
HEADLINE = ("green", "chrom", "pos", "trace", "physnet", "factorizephys")
ABLATION = ("green", "ica", "chrom", "pos", "pos_mask", "pos_wiener", "trace_v1", "trace_v2", "trace_v3",
            "physnet", "factorizephys")
# Method identity in the gap chart: validated categorical slots, TRACE in ink.
METHOD_COLOUR = {"pos": "#eb6834", "chrom": "#1baf7a", "physnet": "#4a3aa7", "factorizephys": "#e87ba4",
                 "trace": INK}
LOSSLESS_X = 3200  # where the lossless point sits on the log2 bitrate axis

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": RULE, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": RULE, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "legend.frameon": False, "lines.linewidth": 2.0, "lines.markersize": 6,
})


def rate_axis(ax, bitrates):
    ax.set_xscale("log", base=2)
    ticks = list(bitrates) + [LOSSLESS_X]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(b) for b in bitrates] + ["lossless"])
    ax.minorticks_off()
    ax.axvspan(2000, 2600, color=SURFACE, zorder=3)  # visual break before lossless
    ax.set_xlabel("bitrate (kbps, 640x480 at 30 fps)")


def fan(cells, methods, codec, bitrates, title, path, sim):
    n = len(methods)
    cols = 3 if n > 4 else n
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(3.4 * cols, 2.9 * rows), sharey=True, squeeze=False)
    for ax, m in zip(axes.ravel(), methods):
        for grp, (col, mk, lab) in TONE.items():
            d = cells[(cells["method"] == m) & (cells["group"] == grp)]
            lossy = d[(d["codec"] == codec) & (d["pix_fmt"] == "yuv420p") & (~d["lossless"])].sort_values("kbps")
            ll = d[d["condition"] == "lossless_rgb"]
            if lossy.empty:
                continue
            ax.fill_between(lossy["kbps"], lossy["ci_low"], lossy["ci_high"], color=col, alpha=0.12, lw=0)
            ax.plot(lossy["kbps"], lossy["mae"], color=col, marker=mk, label=lab, zorder=4)
            if not ll.empty:
                v = ll.iloc[0]
                ax.errorbar([LOSSLESS_X], [v["mae"]], yerr=[[v["mae"] - v["ci_low"]], [v["ci_high"] - v["mae"]]],
                            color=col, marker=mk, capsize=3, lw=1.5, zorder=4)
            ax.annotate("I-III" if grp == "I-III" else "IV-VI", (lossy["kbps"].iloc[0], lossy["mae"].iloc[0]),
                        xytext=(-4, 6), textcoords="offset points", ha="right", color=INK2, fontsize=8)
        ax.set_title(METHOD_LABEL.get(m, m))
        rate_axis(ax, bitrates)
        ax.set_ylim(bottom=0)
    for ax in axes.ravel()[n:]:
        ax.set_visible(False)
    axes[0, 0].set_ylabel("MAE (BPM), 95% CI")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=2, fontsize=8)
    fig.suptitle(title + (" (SIMULATED PILOT)" if sim else ""), x=0.01, ha="left", fontsize=11,
                 fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def gap_chart(cells, methods, codecs, bitrates, path, sim):
    fig, axes = plt.subplots(1, len(codecs), figsize=(3.6 * len(codecs), 3.0), sharey=True, squeeze=False)
    for ax, codec in zip(axes[0], codecs):
        for m in methods:
            d = cells[cells["method"] == m]
            pv = d.pivot_table(index="condition", columns="group", values="mae")
            if pv.empty or "IV-VI" not in pv or "I-III" not in pv:
                continue
            gap = (pv["IV-VI"] - pv["I-III"]).rename("gap").reset_index()
            meta = d.drop_duplicates("condition").set_index("condition")
            gap = gap.join(meta[["codec", "kbps", "pix_fmt", "lossless"]], on="condition")
            lossy = gap[(gap["codec"] == codec) & (gap["pix_fmt"] == "yuv420p") & (~gap["lossless"])].sort_values("kbps")
            ll = gap[gap["condition"] == "lossless_rgb"]
            col = METHOD_COLOUR.get(m, INK2)
            lw = 2.6 if m == "trace" else 1.6
            ax.plot(lossy["kbps"], lossy["gap"], color=col, lw=lw, marker="o", ms=4, label=METHOD_LABEL[m])
            if not ll.empty:
                ax.plot([LOSSLESS_X], [ll["gap"].iloc[0]], color=col, marker="D", ms=5)
            if len(lossy):
                ax.annotate(METHOD_LABEL[m], (lossy["kbps"].iloc[0], lossy["gap"].iloc[0]), xytext=(-4, 0),
                            textcoords="offset points", ha="right", va="center", color=INK2, fontsize=7)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_title(codec.upper().replace("H26", "H.26"))
        rate_axis(ax, bitrates)
    axes[0, 0].set_ylabel("MAE gap, IV-VI minus I-III (BPM)")
    axes[0, -1].legend(loc="upper right", fontsize=7)
    fig.suptitle("Does the skin-tone gap widen as bitrate falls?" + (" (SIMULATED PILOT)" if sim else ""),
                 x=0.01, ha="left", fontsize=11, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def bland_altman_fig(df, path, sim, methods=("pos", "trace"), conds=("lossless_rgb", "h264_100k")):
    fig, axes = plt.subplots(len(methods), len(conds), figsize=(3.6 * len(conds), 2.9 * len(methods)),
                             sharex=True, sharey=True, squeeze=False)
    for i, m in enumerate(methods):
        for j, c in enumerate(conds):
            ax = axes[i, j]
            d = df[(df["method"] == m) & (df["condition"] == c)]
            for grp, (col, mk, lab) in TONE.items():
                g = d[np.where(d["fitzpatrick"] >= 4, "IV-VI", "I-III") == grp]
                if g.empty:
                    continue
                ba = bland_altman(g["est_bpm"].to_numpy(), g["ref_bpm"].to_numpy())
                ax.scatter(ba.mean, ba.diff, s=10, color=col, marker=mk, alpha=0.5, lw=0, label=lab)
                for y, ls in ((ba.bias, "-"), (ba.loa_low, "--"), (ba.loa_high, "--")):
                    ax.axhline(y, color=col, lw=1.0, ls=ls)
                ax.annotate(f"{grp}: bias {ba.bias:+.1f}, LoA {ba.loa_low:+.0f} to {ba.loa_high:+.0f}",
                            (0.02, 0.95 if grp == "I-III" else 0.85), xycoords="axes fraction", fontsize=7, color=INK2)
            ax.set_title(f"{METHOD_LABEL[m]}, {c.replace('_', ' ')}")
            if i == len(methods) - 1:
                ax.set_xlabel("mean of estimate and reference (BPM)")
            if j == 0:
                ax.set_ylabel("estimate minus reference (BPM)")
    axes[0, -1].legend(loc="lower right", fontsize=7)
    fig.suptitle("Bland-Altman by skin-tone group" + (" (SIMULATED PILOT)" if sim else ""), x=0.01, ha="left",
                 fontsize=11, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def ablation_fig(cells, methods, cond, path, sim, title):
    fig, ax = plt.subplots(figsize=(max(7.2, 1.05 * len(methods) + 1.5), 3.2))
    x = np.arange(len(methods))
    wdt = 0.38
    for k, (grp, (col, mk, lab)) in enumerate(TONE.items()):
        vals, lo, hi = [], [], []
        for m in methods:
            r = cells[(cells["method"] == m) & (cells["condition"] == cond) & (cells["group"] == grp)]
            v = r.iloc[0] if len(r) else None
            vals.append(v["mae"] if v is not None else np.nan)
            lo.append(v["mae"] - v["ci_low"] if v is not None else 0)
            hi.append(v["ci_high"] - v["mae"] if v is not None else 0)
        pos = x + (k - 0.5) * (wdt + 0.02)
        ax.bar(pos, vals, wdt, color=col, label=lab, zorder=3)
        ax.errorbar(pos, vals, yerr=[lo, hi], fmt="none", ecolor=INK2, capsize=2, lw=1, zorder=4)
        for p, v in zip(pos, vals):
            if np.isfinite(v):
                ax.annotate(f"{v:.1f}", (p, v), xytext=(0, 2), textcoords="offset points", ha="center",
                            fontsize=7, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([METHOD_LABEL[m] for m in methods])
    ax.set_ylabel("MAE (BPM), 95% CI")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title(title + (" (SIMULATED PILOT)" if sim else ""), loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def chroma_fig(cells, method, path, sim):
    steps = [("lossless_rgb", "RGB\nlossless"), ("lossless_yuv444", "YUV 4:4:4\nlossless"),
             ("lossless_yuv420", "YUV 4:2:0\nlossless"), ("h264_444_400k", "H.264 4:4:4\n400 kbps"),
             ("h264_400k", "H.264 4:2:0\n400 kbps"), ("h264_444_100k", "H.264 4:4:4\n100 kbps"),
             ("h264_100k", "H.264 4:2:0\n100 kbps")]
    fig, ax = plt.subplots(figsize=(7.6, 3.0))
    x = np.arange(len(steps))
    for grp, (col, mk, lab) in TONE.items():
        ys = []
        for c, _ in steps:
            r = cells[(cells["method"] == method) & (cells["condition"] == c) & (cells["group"] == grp)]
            ys.append(r["mae"].iloc[0] if len(r) else np.nan)
        ax.plot(x, ys, color=col, marker=mk, label=lab)
    ax.set_xticks(x)
    ax.set_xticklabels([s[1] for s in steps], fontsize=7)
    ax.set_ylabel("MAE (BPM)")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8)
    ax.set_title(f"{METHOD_LABEL[method]}: which step of the codec does the damage?"
                 + (" (SIMULATED PILOT)" if sim else ""), loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def success_fig(df, methods, codec, bitrates, path, sim):
    """Share of windows within 5 BPM, by group and bitrate: the companion to
    MAE that shows whether a group is already at its failure plateau."""
    d = df[(df["codec"] == codec) & (df["pix_fmt"] == "yuv420p") | (df["condition"] == "lossless_rgb")].copy()
    d["ok"] = ((d["est_bpm"] - d["ref_bpm"]).abs() <= 5.0).astype(float)
    d["group"] = np.where(d["fitzpatrick"] >= 4, "IV-VI", "I-III")
    per = d.groupby(["method", "group", "condition", "kbps", "subject"], dropna=False)["ok"].mean().reset_index()
    fig, axes = plt.subplots(1, len(methods), figsize=(3.3 * len(methods), 2.9), sharey=True, squeeze=False)
    for ax, m in zip(axes[0], methods):
        for grp, (col, mk, lab) in TONE.items():
            g = per[(per["method"] == m) & (per["group"] == grp)]
            lossy = g[g["condition"] != "lossless_rgb"].groupby("kbps")["ok"].mean()
            ll = g[g["condition"] == "lossless_rgb"]["ok"].mean()
            ax.plot(lossy.index, 100 * lossy.values, color=col, marker=mk, label=lab)
            ax.plot([LOSSLESS_X], [100 * ll], color=col, marker=mk)
        ax.set_title(METHOD_LABEL.get(m, m))
        rate_axis(ax, bitrates)
        ax.set_ylim(0, 100)
    axes[0, 0].set_ylabel("windows within 5 BPM (%)")
    axes[0, 0].legend(fontsize=8, loc="upper left")
    title = ("Success rate by skin-tone group: do both groups meet at the failure plateau?" if len(methods) > 2
             else "Windows within 5 BPM, H.264")
    fig.suptitle(title + (" (SIMULATED PILOT)" if sim else ""), x=0.01, ha="left", fontsize=11, fontweight="bold",
                 color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def mechanism_fig(path, sim):
    p = ROOT / "results" / "harness_validation_sim.json"
    if not p.exists():
        return
    h = json.loads(p.read_text())
    mech = h.get("pulse_fidelity")
    if mech is None:
        return
    fig, axes = plt.subplots(1, 4, figsize=(12, 2.8), sharey=True)
    for ax, codec in zip(axes, ("h264", "h265", "vp9", "vp8")):
        for grp, key in (("I-III", "II"), ("IV-VI", "VI")):
            col, mk, _ = TONE[grp]
            pts = sorted((v["kbps"], v[key]) for k, v in mech.items()
                         if v["codec"] == codec and v["kbps"] and v["pix"] == "yuv420p")
            ax.plot([a for a, _ in pts], [b for _, b in pts], color=col, marker=mk, label=f"type {key}")
            ax.plot([LOSSLESS_X], [mech["lossless_rgb"][key]], color=col, marker=mk)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_ylim(-0.2, 1.0)
        ax.set_title(codec.upper().replace("H26", "H.26"))
        ax.set_xscale("log", base=2)
        ax.set_xticks([100, 200, 400, 800, 1600, LOSSLESS_X])
        ax.set_xticklabels(["100", "200", "400", "800", "1600", "lossless"])
        ax.minorticks_off()
        ax.set_xlabel("kbps")
    axes[0].set_ylabel("pulse fidelity (correlation)")
    axes[-1].legend(fontsize=8)
    fig.suptitle("Mechanism: how much of the pulse survives the codec, still face" + (" (SIMULATED)" if sim else ""),
                 x=0.01, ha="left", fontsize=11, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sim")
    args = ap.parse_args()
    df = pd.read_csv(ROOT / "results" / f"grid_{args.tag}.csv")
    sim = bool((df["source"] == "simulated").any())
    figs = ROOT / "results" / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    if df["fitzpatrick"].isna().all():
        raise SystemExit(
            "No Fitzpatrick labels in this grid, so no skin-tone comparison is possible. "
            "Run scripts/make_labels_template.py <dataset>, fill in fitzpatrick.csv, then rerun "
            "run_grid.py (stage 2 is enough) and this script.")
    errs = subject_condition_errors(df)
    cells = cell_table(errs)
    cells.to_csv(ROOT / "results" / f"cells_{args.tag}.csv", index=False)
    present = set(df["method"])
    methods = [m for m in HEADLINE if m in present]
    ablation = [m for m in ABLATION if m in present]
    codecs = [c for c in ("h264", "h265", "vp9") if c in set(df["codec"])]
    bitrates = sorted(int(k) for k in df.loc[~df["lossless"], "kbps"].dropna().unique())

    inter = []
    for m in ablation:
        for c in codecs:
            if not ((errs["method"] == m) & (errs["codec"] == c)).any():
                continue  # neural baselines run on the H.264 ladder only
            try:
                inter.append(interaction(errs, m, c).__dict__)
            except Exception as exc:
                print(f"  interaction {m} {c} failed: {exc}")
    inter = pd.DataFrame(inter)
    inter.to_csv(ROOT / "results" / f"interaction_{args.tag}.csv", index=False)
    print("Interaction (BPM change in the dark-minus-light gap per doubling of bitrate; negative = widens)")
    print(inter[["method", "codec", "coef", "ci_low", "ci_high", "p", "boot_low", "boot_high", "log_p",
                 "gap_lossless", "gap_lowest"]].round(3).to_string(index=False))

    # Power for real-data planning, from the pilot's own variance components.
    pos = errs[(errs["method"] == "pos") & (errs["codec"] == "h264") & (~errs["lossless"])]
    subj = pos.groupby("subject")["err"].mean()
    sd_subject = float(subj.std())
    sd_resid = float((pos["err"] - pos["subject"].map(subj)).std())
    pilot = inter[(inter["method"] == "pos") & (inter["codec"] == "h264")]
    effect = abs(float(pilot["coef"].iloc[0])) if len(pilot) else 1.0
    power_rows = []
    for eff in sorted({round(max(effect, 0.25), 2), round(max(effect, 0.25) / 2, 2), 0.5, 1.0}):
        for n in (6, 10, 15, 20, 30, 40):
            power_rows.append({"effect_bpm_per_doubling": eff, "n_per_group": n,
                               "power": power_interaction(eff, sd_subject, sd_resid, n, n_sim=200)})
    power = pd.DataFrame(power_rows)
    power.to_csv(ROOT / "results" / f"power_{args.tag}.csv", index=False)
    print("\nPower (alpha 0.05) for the interaction, pilot SDs: subject", round(sd_subject, 2),
          "residual", round(sd_resid, 2))
    print(power.pivot(index="n_per_group", columns="effect_bpm_per_doubling", values="power").round(2).to_string())

    fan(cells, methods, "h264", bitrates,
        "Headline: MAE vs H.264 bitrate by skin-tone group", figs / f"{args.tag}_fan_h264.png", sim)
    for c in codecs:
        if c != "h264":
            fan(cells, [m for m in methods if m not in ("physnet", "factorizephys")], c, bitrates,
                f"MAE vs {c.upper()} bitrate", figs / f"{args.tag}_fan_{c}.png", sim)
    gap_chart(cells, [m for m in ("pos", "chrom", "physnet", "factorizephys", "trace") if m in methods], codecs,
              bitrates, figs / f"{args.tag}_gap.png", sim)
    bland_altman_fig(df, figs / f"{args.tag}_bland_altman.png", sim)
    ablation_fig(cells, ablation, "lossless_rgb", figs / f"{args.tag}_ablation_lossless.png", sim,
                 "Ablation, lossless video")
    ablation_fig(cells, ablation, "h264_200k", figs / f"{args.tag}_ablation_h264_200k.png", sim,
                 "Ablation, H.264 at 200 kbps")
    chroma_fig(cells, "pos", figs / f"{args.tag}_chroma_steps_pos.png", sim)
    success_fig(df, [m for m in ("chrom", "pos", "trace", "factorizephys") if m in present], "h264", bitrates,
                figs / f"{args.tag}_success_h264.png", sim)
    success_fig(df, [m for m in ("pos", "trace") if m in present], "h264", bitrates,
                figs / f"{args.tag}_success_h264_compact.png", sim)
    if sim:
        mechanism_fig(figs / "sim_mechanism.png", sim)

    summary = {"source": "simulated" if sim else "real", "n_subjects": int(df["subject"].nunique()),
               "n_rows": int(len(df)), "bitrates": bitrates, "codecs": codecs,
               "interaction": inter.to_dict(orient="records"),
               "lossless_mae": {f"{r.method}|{r.group}": r.mae for r in cells[cells["condition"] == "lossless_rgb"].itertuples()},
               "h264_100k_mae": {f"{r.method}|{r.group}": r.mae for r in cells[cells["condition"] == "h264_100k"].itertuples()},
               "power_pilot_sd": {"subject": sd_subject, "residual": sd_resid}}
    (ROOT / "results" / f"summary_{args.tag}.json").write_text(json.dumps(summary, indent=1, default=float))
    print(f"\nfigures in {figs}")


if __name__ == "__main__":
    main()
