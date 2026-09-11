"""Neural baselines (T6): pretrained rPPG-Toolbox checkpoints, inference only.

Runs in the separate `.venv-nn` environment (torch lives there, never in the
core pipeline). Reads the 72x72 face crops the grid runner saved for each
condition, and writes one predicted pulse per model per condition. Nothing
is trained. The predictions join the results table as baseline methods; they
never enter the TRACE estimation path (CLAUDE.md Rule 1.3.1).

Checkpoints (both trained on PURE, so evaluating on UBFC-rPPG or our
simulation involves no train/test overlap):
    physnet        PURE_PhysNet_DiffNormalized.pth   (Yu et al. BMVC 2019)
    factorizephys  PURE_FactorizePhys_FSAM_Res.pth   (Joshi et al. NeurIPS 2024)

Usage (from the core scripts, or by hand):
    .venv-nn/Scripts/python.exe scripts/nn_infer.py <work_dir> <out_dir> [--models physnet,factorizephys]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
TOOLBOX = ROOT / "third_party" / "rPPG-Toolbox"
CKPT = TOOLBOX / "final_model_release"
sys.path.insert(0, str(TOOLBOX))

torch.set_num_threads(int(__import__("os").environ.get("NN_THREADS", "4")))


def diff_normalize(frames: np.ndarray) -> np.ndarray:
    """rPPG-Toolbox 'DiffNormalized': normalised frame differences / std."""
    f = frames.astype(np.float32)
    d = (f[1:] - f[:-1]) / (f[1:] + f[:-1] + 1e-7)
    d = d / (np.std(d) + 1e-12)
    d = np.concatenate([d, np.zeros_like(d[:1])], axis=0)
    d[np.isnan(d)] = 0
    return d


def standardize(frames: np.ndarray) -> np.ndarray:
    f = frames.astype(np.float32)
    f = (f - f.mean()) / (f.std() + 1e-12)
    f[np.isnan(f)] = 0
    return f


def _load(model: torch.nn.Module, path: Path, allow_missing: tuple[str, ...] = ()) -> torch.nn.Module:
    """Load a checkpoint and refuse any key mismatch we have not explained."""
    state = torch.load(path, map_location="cpu", weights_only=False)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    state = {k.replace("module.", "", 1): v for k, v in state.items()}
    missing, unexpected = model.load_state_dict(state, strict=False)
    missing = [k for k in missing if k not in allow_missing]
    if missing or unexpected:
        raise RuntimeError(f"{path.name}: missing {missing}, unexpected {unexpected}")
    return model.eval()


def chunks(n: int, length: int) -> list[tuple[int, int]]:
    """Non-overlapping chunks, with a final chunk aligned to the end."""
    out = [(s, s + length) for s in range(0, n - length + 1, length)]
    if out and out[-1][1] < n:
        out.append((n - length, n))
    return out


class PhysNetRunner:
    name = "physnet"
    length = 128

    def __init__(self):
        from neural_methods.model.PhysNet import PhysNet_padding_Encoder_Decoder_MAX

        self.model = _load(PhysNet_padding_Encoder_Decoder_MAX(frames=self.length),
                           CKPT / "PURE_PhysNet_DiffNormalized.pth")

    @torch.no_grad()
    def __call__(self, crops: np.ndarray) -> np.ndarray:
        x = diff_normalize(crops)  # (n, H, W, 3)
        n = len(x)
        out = np.zeros(n)
        filled = np.zeros(n, bool)
        for a, b in chunks(n, self.length):
            t = torch.from_numpy(x[a:b]).permute(3, 0, 1, 2).unsqueeze(0)  # NCDHW
            pred = self.model(t)[0].reshape(-1).numpy()
            # The final chunk overlaps the previous one; keep only new samples.
            sel = ~filled[a:b]
            out[a:b][sel] = pred[sel]
            filled[a:b] = True
        # The network predicts the derivative (diff-normalised label): integrate.
        return np.cumsum(out)


class FactorizePhysRunner:
    name = "factorizephys"
    length = 160

    def __init__(self):
        from neural_methods.model.FactorizePhys.FactorizePhys import FactorizePhys

        # The checkpoint contains the FSAM convolution weights, so FSAM must be
        # on (with it off, four trained tensors would be silently dropped).
        # `rppg_head.bias1` is absent from the checkpoint by construction: the
        # model creates it as nn.Parameter(1.0).to(device), which on a GPU
        # returns an unregistered tensor, so it was never trained or saved and
        # stayed at 1.0. On CPU it registers at the same initial 1.0.
        md_config = {"FRAME_NUM": self.length, "MD_TYPE": "NMF", "MD_FSAM": True, "MD_TRANSFORM": "T_KAB",
                     "MD_S": 1, "MD_R": 1, "MD_STEPS": 4, "MD_INFERENCE": True, "MD_RESIDUAL": True}
        self.model = _load(FactorizePhys(frames=self.length, md_config=md_config, in_channels=3,
                                         dropout=0.1, device=torch.device("cpu")),
                           CKPT / "PURE_FactorizePhys_FSAM_Res.pth", allow_missing=("rppg_head.bias1",))

    @torch.no_grad()
    def __call__(self, crops: np.ndarray) -> np.ndarray:
        x = crops.astype(np.float32)  # 'Raw' input
        n = len(x)
        out = np.zeros(n)
        filled = np.zeros(n, bool)
        for a, b in chunks(n, self.length):
            seg = x[a:b]
            # FactorizePhys differences frames internally and expects one extra frame.
            seg = np.concatenate([seg, seg[-1:]], axis=0)
            t = torch.from_numpy(seg).permute(3, 0, 1, 2).unsqueeze(0)
            pred = self.model(t)
            pred = pred[0] if isinstance(pred, (tuple, list)) else pred
            pred = pred.reshape(-1).numpy()[: b - a]
            pred = (pred - pred.mean()) / (pred.std() + 1e-12)
            sel = ~filled[a:b]
            out[a:b][sel] = pred[sel]
            filled[a:b] = True
        return out  # standardised pulse, not a derivative


RUNNERS = {"physnet": PhysNetRunner, "factorizephys": FactorizePhysRunner}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--models", default="physnet,factorizephys")
    ap.add_argument("--keep-crops", action="store_true")
    args = ap.parse_args()
    runners = [RUNNERS[m]() for m in args.models.split(",") if m]
    for crop_file in sorted(args.work_dir.glob("*_crops.npy")):
        cond = crop_file.name[: -len("_crops.npy")]
        crops = np.load(crop_file)
        preds = {r.name: r(crops).astype(np.float32) for r in runners}
        np.savez_compressed(args.out_dir / f"{cond}_nn.npz", **preds)
        if not args.keep_crops:
            crop_file.unlink()
        print(f"{cond}: " + ", ".join(preds), flush=True)


if __name__ == "__main__":
    main()
