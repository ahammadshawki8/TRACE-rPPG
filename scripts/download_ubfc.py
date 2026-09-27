"""Download a subset of UBFC-rPPG DATASET_2 from the public Kaggle mirror.

    .venv/Scripts/python.exe scripts/download_ubfc.py --dest D:/datasets/ubfc --subjects 1 3 5 8

The mirror (malekdinarito/ubfc-rppg-dataset, about 75 GB for 42 subjects)
serves single files without an account, so only the chosen subjects are
fetched: vid.avi (about 1.3 to 1.9 GB) and ground_truth.txt each. Files are
written to <name>.part and renamed when complete, and a partial file is
resumed with an HTTP range request, so the script can be stopped and rerun.
Bobbia et al. 2017; research use only, never redistributed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

KAGGLE = "malekdinarito/ubfc-rppg-dataset"
URL = "https://www.kaggle.com/api/v1/datasets/download/{ds}?fileName={name}"
LIST = "https://www.kaggle.com/api/v1/datasets/list/{ds}?pageSize=200"


class Progress:
    """Overall progress across every chosen file. Prints one PROGRESS line at
    each 10 percent step (with an ETA from the rate of this run), so a long
    download can be watched without reading every per-file line."""

    def __init__(self, total: int, already: int):
        self.total, self.done, self.start_done = total, already, already
        self.t0 = time.time()
        self.next_step = int(100 * already / total) // 10 * 10 + 10 if total else 100
        print(f"PROGRESS {100 * already / max(1, total):.0f}% at start: {already / 1e9:.1f} of {total / 1e9:.1f} GB already here", flush=True)

    def add(self, n: int) -> None:
        self.done += n
        pct = 100 * self.done / max(1, self.total)
        while pct >= self.next_step and self.next_step <= 100:
            rate = (self.done - self.start_done) / max(1e-6, time.time() - self.t0)
            left = (self.total - self.done) / rate if rate > 0 else float("inf")
            eta = time.strftime("%H:%M", time.localtime(time.time() + left)) if left < 1e6 else "?"
            print(f"PROGRESS {self.next_step}%: {self.done / 1e9:.1f} of {self.total / 1e9:.1f} GB, "
                  f"{rate / 1e6:.1f} MB/s, about {left / 60:.0f} min left (done near {eta})", flush=True)
            self.next_step += 10


def sizes(ds: str = KAGGLE) -> dict[str, int]:
    out, tok = {}, None
    while True:
        u = LIST.format(ds=ds) + (f"&pageToken={urllib.parse.quote(tok)}" if tok else "")
        d = json.load(urllib.request.urlopen(u, timeout=30))
        out.update({f["name"]: f["totalBytes"] for f in d["datasetFiles"]})
        tok = d.get("nextPageTokenNullable") or d.get("nextPageToken")
        if not tok:
            return out


PROG: Progress | None = None
DEFAULT = (1, 3, 5, 8, 10, 12, 14, 17, 20, 23, 26, 31, 38, 45)


def fetch(name: str, out: Path, ds: str = KAGGLE) -> None:
    if out.exists():
        print(f"  have {name}")
        return
    part = out.with_name(out.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(URL.format(ds=ds, name=name), headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        if have and r.status != 206:  # server ignored the range: start over
            have = 0
        total = have + int(r.headers.get("Content-Length") or 0)
        t0, last = time.time(), 0.0
        with open(part, "ab" if have else "wb") as f:
            done = have
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if PROG:
                    PROG.add(len(chunk))
                if time.time() - last > 15:
                    last = time.time()
                    rate = (done - have) / max(1e-6, last - t0) / 1e6
                    print(f"  {name}: {done / 1e9:.2f} / {total / 1e9:.2f} GB, {rate:.1f} MB/s", flush=True)
    part.replace(out)
    print(f"  done {name} ({out.stat().st_size / 1e9:.2f} GB)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="D:/datasets/ubfc")
    ap.add_argument("--subjects", type=int, nargs="*", default=list(DEFAULT))
    a = ap.parse_args()
    dest = Path(a.dest)
    global PROG
    size = sizes()
    names = [(f"subject{s}/{fn}", dest / f"subject{s}" / fn) for s in a.subjects for fn in ("ground_truth.txt", "vid.avi")]
    total = sum(size.get(n, 0) for n, _ in names)

    def present(out: Path) -> int:
        part = out.with_name(out.name + ".part")
        return out.stat().st_size if out.exists() else part.stat().st_size if part.exists() else 0

    PROG = Progress(total, sum(present(o) for _, o in names))
    for s in a.subjects:
        folder = dest / f"subject{s}"
        folder.mkdir(parents=True, exist_ok=True)
        print(f"subject{s}", flush=True)
        for fn in ("ground_truth.txt", "vid.avi"):
            for attempt in range(5):
                try:
                    fetch(f"subject{s}/{fn}", folder / fn)
                    break
                except Exception as exc:  # network hiccup: resume from the .part file
                    print(f"  retry {attempt + 1} after {exc}", flush=True)
                    time.sleep(10)
            else:
                print(f"PROGRESS WARNING: gave up on subject{s}/{fn}", flush=True)
    print("PROGRESS finished", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
