"""T7: run the full grid on a simulated cohort (or a real dataset).

    subject x condition (3 lossless controls, 3 codecs x 5 bitrates, 4:4:4 ablation)
            x method (green, ICA, CHROM, POS, TRACE, PhysNet, FactorizePhys)

Stage 1 is parallel over subjects and resumable: rerunning skips finished
work. Each worker renders one lossless subject, encodes and decodes every
condition, stores traces and face crops, runs the neural baselines in the
separate `.venv-nn` environment, then deletes every video and crop file.

Stage 2 evaluates every stored trace into one tidy CSV:
    results/grid_<tag>.csv   one row per subject, condition, method, window

Usage:
    .venv/Scripts/python.exe scripts/run_grid.py                 # simulated pilot
    .venv/Scripts/python.exe scripts/run_grid.py --dataset data/ubfc --tag ubfc
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from _common import ROOT, cohort
from tracerppg.compress import grid_conditions
from tracerppg.grid import evaluate_subject, process_subject
from tracerppg.simulate import simulate_recording

NN_PY = ROOT / ".venv-nn" / "Scripts" / "python.exe"
NN_MODELS = ("physnet", "factorizephys")
# Neural baselines run on the lossless control and the H.264 ladder: enough
# for the classical-versus-learned comparison, at a quarter of the cost.
NN_CONDITIONS = {"lossless_rgb", "h264_100k", "h264_200k", "h264_400k", "h264_800k", "h264_1600k"}


def stage1(job: dict) -> str:
    out_root, work_root, crops_root = Path(job["out_root"]), Path(job["work_root"]), Path(job["crops_root"])
    subject = job["subject"]
    out = out_root / subject
    conds = grid_conditions()
    nn = job["nn"]
    have_crops = lambda c: (crops_root / subject / f"{c}_crops.npy").exists() or (out / f"{c}_nn.npz").exists()  # noqa: E731
    done = all((out / f"{c.name}.npz").exists() for c in conds) and (
        not nn or all(have_crops(c) for c in NN_CONDITIONS))
    if done:
        return f"{subject}: already done"
    t0 = time.time()
    if job.get("cfg") is not None:
        from tracerppg.simulate import SimConfig
        src = work_root / f"{subject}_src"
        if not (src / "vid.mkv").exists():
            simulate_recording(src, SimConfig(**job["cfg"]))
    else:
        src = Path(job["source"])
    process_subject(src, subject, out_root, work_root, conds, crop_size=72 if nn else None,
                    delete_source=job.get("cfg") is not None, crop_conditions=NN_CONDITIONS,
                    crops_root=crops_root, extra_meta=job.get("meta"))
    shutil.rmtree(work_root / subject, ignore_errors=True)
    if job.get("cfg") is not None:
        shutil.rmtree(work_root / f"{subject}_src", ignore_errors=True)
    return f"{subject}: {time.time() - t0:.0f} s"


def stage_nn(jobs: list[dict], parallel: int = 2) -> None:
    """Neural inference in the separate environment, a few subjects at a time.

    Each process holds one subject's crops and both models (about 1.2 GB), so
    parallelism is set by free memory, not by cores.
    """
    import os
    from concurrent.futures import ThreadPoolExecutor

    env = dict(os.environ, NN_THREADS=str(max(4, 16 // parallel)))

    def one(j):
        crops = Path(j["crops_root"]) / j["subject"]
        if not crops.exists() or not any(crops.glob("*_crops.npy")):
            return f"{j['subject']}: nothing to do"
        t0 = time.time()
        subprocess.run([str(NN_PY), str(ROOT / "scripts" / "nn_infer.py"), str(crops),
                        str(Path(j["out_root"]) / j["subject"]), "--models", ",".join(NN_MODELS)],
                       check=True, capture_output=True, text=True, env=env)
        return f"{j['subject']}: {time.time() - t0:.0f} s"

    with ThreadPoolExecutor(max_workers=parallel) as ex:
        for i, msg in enumerate(ex.map(one, jobs), 1):
            print(f"  nn [{i}/{len(jobs)}] {msg}", flush=True)


def stage2(args) -> list[dict]:
    folder, p, nn = args
    return evaluate_subject(Path(folder), params=p, nn_models=NN_MODELS if nn else ())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sim")
    ap.add_argument("--dataset", type=Path, default=None, help="real dataset root (UBFC layout)")
    ap.add_argument("--n-per-type", type=int, default=8)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--seed0", type=int, default=3000)
    ap.add_argument("--max-subjects", type=int, default=0, help="first N subjects in interleaved order")
    ap.add_argument("--work-root", type=Path, default=None,
                    help="scratch for encodes and crops; put it on the same drive as a large dataset")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--no-nn", action="store_true")
    ap.add_argument("--stage", choices=("all", "1", "nn", "2"), default="all")
    args = ap.parse_args()

    nn = not args.no_nn and NN_PY.exists() and (ROOT / "third_party" / "rPPG-Toolbox").exists()
    out_root = ROOT / "results" / "raw" / args.tag
    scratch = Path(args.work_root) if args.work_root else ROOT / "data"
    work_root = scratch / "work" / args.tag
    crops_root = scratch / "crops" / args.tag
    for p in (out_root, work_root, crops_root):
        p.mkdir(parents=True, exist_ok=True)

    if args.dataset is not None:
        # Recursive: a download keeps its own nesting and may live on another
        # drive. Skin-type labels come from fitzpatrick.csv beside the data.
        from tracerppg.datasets import load_dataset
        recs = load_dataset(args.dataset)
        jobs = [{"subject": r.subject, "source": str(r.video_path.parent), "cfg": None,
                 "meta": {k: v for k, v in (("fitzpatrick", r.fitzpatrick),) if v is not None}} for r in recs]
        missing = [r.subject for r in recs if r.fitzpatrick is None]
        if missing:
            print(f"  note: {len(missing)} of {len(recs)} subjects have no Fitzpatrick label; "
                  "run scripts/make_labels_template.py to add them (skin-tone analysis needs them)", flush=True)
    else:
        from dataclasses import asdict
        cfgs = cohort(n_per_type=args.n_per_type, duration_s=args.duration, seed0=args.seed0)
        # Interleave skin types so that the subjects finished at any moment
        # form a balanced cohort (one of each type, then the next of each...).
        cfgs.sort(key=lambda c: (c.seed % 100, c.fitzpatrick))
        # Trim with --max-subjects, never by changing --n-per-type: heart rates
        # are drawn from one sequential stream, so n-per-type changes every
        # subject's configuration after the first type.
        if args.max_subjects:
            cfgs = cfgs[: args.max_subjects]
        jobs = [{"subject": f"s{c.fitzpatrick}_{c.seed}", "cfg": asdict(c)} for c in cfgs]
    for j in jobs:
        j.update(out_root=str(out_root), work_root=str(work_root), crops_root=str(crops_root), nn=nn)

    print(f"{len(jobs)} subjects, {len(grid_conditions())} conditions, neural baselines: {nn}", flush=True)
    if args.stage in ("all", "1"):
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(stage1, j) for j in jobs]
            for i, f in enumerate(as_completed(futs), 1):
                print(f"  [{i}/{len(jobs)}] {f.result()}", flush=True)
    if nn and args.stage in ("all", "nn"):
        stage_nn(jobs)

    if args.stage in ("all", "2"):
        params = json.loads((ROOT / "results" / "fusion_params.json").read_text())
        folders = [str(out_root / j["subject"]) for j in jobs]
        rows = []
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(stage2, [(f, params, nn) for f in folders]):
                rows.extend(r)
        df = pd.DataFrame(rows)
        dest = ROOT / "results" / f"grid_{args.tag}.csv"
        df.to_csv(dest, index=False)
        print(f"wrote {dest} ({len(df)} rows, fusion params {params})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
