"""Write a blank Fitzpatrick label file for a dataset.

Public rPPG datasets do not ship skin-type labels, and the interaction
analysis needs them. This lists every subject it finds and leaves the type
blank for a rater to fill in (printed Fitzpatrick card, two raters where
possible, per deliverables/data_collection_protocol.md).

    .venv/Scripts/python.exe scripts/make_labels_template.py D:/datasets/ubfc

Then edit D:/datasets/ubfc/fitzpatrick.csv and fill the second column with
1 to 6. Rows left blank are ignored, and subjects without a label are
dropped from any skin-tone comparison.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _common import ROOT  # noqa: F401  (puts src on the path)
from tracerppg.datasets import load_dataset, read_labels

if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "ubfc")
    recs = load_dataset(root)
    if not recs:
        print(f"No subject folders (ground_truth.txt or gtdump.xmp) under {root}")
        raise SystemExit(1)
    dest = root / "fitzpatrick.csv"
    existing = read_labels(root)
    lines = ["subject,fitzpatrick  # 1 to 6, leave blank if not rated"]
    lines += [f"{r.subject},{existing.get(r.subject, '')}" for r in recs]
    dest.write_text("\n".join(lines) + "\n")
    print(f"wrote {dest} with {len(recs)} subjects ({len(existing)} already labelled)")
    print("Fill the second column, then rerun the grid and analysis.")
