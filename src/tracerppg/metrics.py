"""Agreement metrics between estimated and reference heart rate.

The standard trio in rPPG papers is MAE, RMSE and Pearson r. Bland-Altman
adds what an average hides: whether the error is a systematic bias, and how
wide the band is that 95 percent of differences fall inside (Bland and
Altman 1986). Confidence intervals come from bootstrapping over subjects,
because windows from one subject are not independent of each other.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def mae(est: np.ndarray, ref: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(est) - np.asarray(ref))))


def rmse(est: np.ndarray, ref: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(est) - np.asarray(ref)) ** 2)))


def pearson(est: np.ndarray, ref: np.ndarray) -> float:
    est, ref = np.asarray(est, float), np.asarray(ref, float)
    if np.std(est) < 1e-12 or np.std(ref) < 1e-12:
        return float("nan")
    return float(np.corrcoef(est, ref)[0, 1])


def within(est: np.ndarray, ref: np.ndarray, tol_bpm: float = 5.0) -> float:
    """Fraction of windows within a tolerance (5 BPM is common in the field)."""
    return float(np.mean(np.abs(np.asarray(est) - np.asarray(ref)) <= tol_bpm))


@dataclass
class BlandAltman:
    bias: float
    sd: float
    loa_low: float
    loa_high: float
    mean: np.ndarray
    diff: np.ndarray


def bland_altman(est: np.ndarray, ref: np.ndarray) -> BlandAltman:
    """Mean difference and 95 percent limits of agreement (bias +/- 1.96 SD)."""
    est, ref = np.asarray(est, float), np.asarray(ref, float)
    d = est - ref
    bias, sd = float(np.mean(d)), float(np.std(d, ddof=1)) if len(d) > 1 else 0.0
    return BlandAltman(bias, sd, bias - 1.96 * sd, bias + 1.96 * sd, (est + ref) / 2, d)


def bootstrap_ci(
    values_by_subject: dict[str, np.ndarray],
    stat=np.mean,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Point estimate and CI of `stat` over windows, resampling whole subjects."""
    keys = list(values_by_subject)
    allv = np.concatenate([values_by_subject[k] for k in keys])
    point = float(stat(allv))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(len(keys), len(keys), replace=True)
        boots.append(stat(np.concatenate([values_by_subject[keys[i]] for i in pick])))
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return point, float(lo), float(hi)


def summary(est: np.ndarray, ref: np.ndarray) -> dict[str, float]:
    return {"mae": mae(est, ref), "rmse": rmse(est, ref), "r": pearson(est, ref),
            "within5": within(est, ref), "n": int(len(est))}
