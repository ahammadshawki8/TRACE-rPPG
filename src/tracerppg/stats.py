"""Statistics for the interaction claim. Tier T7.

The poster's claim is about an interaction, not two main effects: does the
effect of bitrate on error differ by skin-tone group? The model, per method
and codec, on per-subject per-condition mean absolute error:

    err ~ log2(kbps) * dark + (1 | subject)

`dark` is 1 for Fitzpatrick IV to VI. The coefficient on log2(kbps):dark is
the fan: how much more (or less) error dark skin gains for every halving of
bitrate. Negative means the gap widens as bitrate falls. Lossless conditions
are excluded from the slope (they have no bitrate) and reported separately.

Errors in rPPG are heavy-tailed (a harmonic lock-on is a 70 BPM error), so a
log(1 + err) version is fitted as a robustness check, and a subject-level
bootstrap interval is reported next to the model's Wald interval.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd


def tone_group(fz: pd.Series) -> pd.Series:
    return np.where(fz >= 4, "IV-VI", "I-III")


def subject_condition_errors(df: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute error per (method, subject, condition): the unit the
    model sees, so windows from one subject do not count as independent."""
    d = df.copy()
    d["abs_err"] = (d["est_bpm"] - d["ref_bpm"]).abs()
    keys = ["method", "subject", "fitzpatrick", "condition", "codec", "kbps", "pix_fmt", "lossless"]
    g = d.groupby(keys, dropna=False, as_index=False).agg(err=("abs_err", "mean"), n=("abs_err", "size"))
    g["dark"] = (g["fitzpatrick"] >= 4).astype(int)
    g["group"] = tone_group(g["fitzpatrick"])
    return g


@dataclass
class Interaction:
    method: str
    codec: str
    coef: float          # BPM change in the dark-minus-light gap per doubling of bitrate
    ci_low: float
    ci_high: float
    p: float
    boot_low: float
    boot_high: float
    log_coef: float      # same, on log(1 + err)
    log_p: float
    n_subjects: int
    gap_lossless: float  # dark minus light MAE, lossless RGB
    gap_lowest: float    # dark minus light MAE at the lowest bitrate

    @property
    def widens(self) -> bool:
        """Gap significantly wider at low bitrate (negative slope, CI below 0)."""
        return self.ci_high < 0


def _fit(data: pd.DataFrame, formula: str):
    import statsmodels.formula.api as smf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res = smf.mixedlm(formula, data, groups=data["subject"]).fit(reml=True, method="lbfgs")
        except Exception:
            res = smf.ols(formula, data).fit(cov_type="cluster", cov_kwds={"groups": data["subject"]})
    return res


def interaction(errs: pd.DataFrame, method: str, codec: str, pix_fmt: str = "yuv420p",
                n_boot: int = 500, seed: int = 0) -> Interaction:
    d = errs[(errs["method"] == method) & (errs["codec"] == codec) & (~errs["lossless"])
             & (errs["pix_fmt"] == pix_fmt)].copy()
    d["lograte"] = np.log2(d["kbps"].astype(float))
    d["logerr"] = np.log1p(d["err"])
    term = "lograte:dark"
    res = _fit(d, "err ~ lograte * dark")
    ci = res.conf_int().loc[term]
    res_log = _fit(d, "logerr ~ lograte * dark")

    # Subject-level bootstrap within each tone group.
    rng = np.random.default_rng(seed)
    subs = {g: d.loc[d["dark"] == g, "subject"].unique() for g in (0, 1)}
    boots = []
    for _ in range(n_boot):
        pick = np.concatenate([rng.choice(subs[g], len(subs[g]), replace=True) for g in (0, 1)])
        b = pd.concat([d[d["subject"] == s].assign(subject=f"{s}#{i}") for i, s in enumerate(pick)])
        x = np.column_stack([np.ones(len(b)), b["lograte"], b["dark"], b["lograte"] * b["dark"]])
        beta, *_ = np.linalg.lstsq(x, b["err"].to_numpy(), rcond=None)
        boots.append(beta[3])
    lo, hi = np.quantile(boots, [0.025, 0.975])

    ll = errs[(errs["method"] == method) & (errs["condition"] == "lossless_rgb")]
    gap_ll = ll.loc[ll["dark"] == 1, "err"].mean() - ll.loc[ll["dark"] == 0, "err"].mean()
    kmin = d["kbps"].min()
    lowest = d[d["kbps"] == kmin]
    gap_lo = lowest.loc[lowest["dark"] == 1, "err"].mean() - lowest.loc[lowest["dark"] == 0, "err"].mean()
    return Interaction(method, codec, float(res.params[term]), float(ci.iloc[0]), float(ci.iloc[1]),
                       float(res.pvalues[term]), float(lo), float(hi), float(res_log.params[term]),
                       float(res_log.pvalues[term]), int(d["subject"].nunique()), float(gap_ll), float(gap_lo))


def cell_table(errs: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    """MAE with a subject-bootstrap 95 percent CI for every cell of the grid."""
    rng = np.random.default_rng(seed)
    rows = []
    for (m, cond, grp), d in errs.groupby(["method", "condition", "group"]):
        v = d["err"].to_numpy()
        boots = [np.mean(rng.choice(v, len(v), replace=True)) for _ in range(n_boot)]
        lo, hi = np.quantile(boots, [0.025, 0.975])
        r = d.iloc[0]
        rows.append({"method": m, "condition": cond, "codec": r["codec"], "kbps": r["kbps"],
                     "pix_fmt": r["pix_fmt"], "lossless": r["lossless"], "group": grp,
                     "mae": float(np.mean(v)), "ci_low": float(lo), "ci_high": float(hi), "n_subjects": len(v)})
    return pd.DataFrame(rows)


def power_interaction(effect: float, sd_subject: float, sd_resid: float, n_per_group: int,
                      rates=(100, 200, 400, 800, 1600), n_sim: int = 300, alpha: float = 0.05,
                      seed: int = 0) -> float:
    """Probability of detecting an interaction of `effect` BPM per doubling.

    Simulates the design (n subjects per group, every subject at every
    bitrate, random subject intercepts) and fits the same model with
    cluster-robust errors, which is fast enough to repeat hundreds of times.
    """
    import statsmodels.formula.api as smf

    rng = np.random.default_rng(seed)
    lr = np.log2(np.array(rates, float))
    lr = lr - lr.mean()
    hits = 0
    for _ in range(n_sim):
        rows = []
        for g in (0, 1):
            for s in range(n_per_group):
                u = rng.normal(0, sd_subject)
                for x in lr:
                    y = 5 + u - 1.0 * x + g * (2.0 + effect * x) + rng.normal(0, sd_resid)
                    rows.append((f"{g}_{s}", x, g, y))
        d = pd.DataFrame(rows, columns=["subject", "lograte", "dark", "err"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = smf.ols("err ~ lograte * dark", d).fit(cov_type="cluster", cov_kwds={"groups": d["subject"]})
        hits += res.pvalues["lograte:dark"] < alpha
    return hits / n_sim
