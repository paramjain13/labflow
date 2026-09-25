"""Simulate a high-content imaging instrument writing a 96-well plate run to disk.

Usage:
    python -m labflow.simulate --out data/incoming --runs 2
    python -m labflow.simulate --out data/incoming --runs 1 --schema-break
"""
import argparse
import csv
import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROWS = "ABCDEFGH"
COLS = range(1, 13)
TREATMENTS = ["DMSO", "CompoundA", "CompoundB", "CompoundC"]
DOSES_UM = [0.1, 1.0, 5.0, 10.0]
BASE_CELLS = 40


def make_cell_image(n_cells: int, size: int = 256, seed: int | None = None) -> np.ndarray:
    """Draw n bright 'nuclei' on a dark background, add noise and blur (like a DAPI channel)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size), dtype=np.uint8)
    for _ in range(n_cells):
        x, y = rng.integers(10, size - 10, size=2)
        radius = int(rng.integers(4, 9))
        intensity = int(rng.integers(150, 255))
        cv2.circle(img, (int(x), int(y)), radius, intensity, -1)
    noise = rng.normal(0, 12, img.shape)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(img, (3, 3), 0)


def expected_cells(treatment: str, dose: float) -> int:
    """Compounds kill cells in a dose-dependent way; DMSO is the vehicle control."""
    if treatment == "DMSO":
        return BASE_CELLS
    potency = {"CompoundA": 20.0, "CompoundB": 8.0, "CompoundC": 60.0}[treatment]
    return max(3, int(BASE_CELLS * max(0.1, 1 - dose / potency)))


def generate_run(out_dir: Path, fault_rate: float = 0.05, schema_break: bool = False,
                 seed: int | None = None) -> Path:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    run_id = f"RUN_{now:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}"
    run_dir = out_dir / run_id
    (run_dir / "images").mkdir(parents=True, exist_ok=True)

    rows = []
    for r in ROWS:
        for c in COLS:
            well_id = f"{r}{c:02d}"
            treatment = TREATMENTS[(c - 1) // 3]           # 3 columns per treatment
            dose = 0.0 if treatment == "DMSO" else DOSES_UM[ROWS.index(r) % 4]
            img = make_cell_image(expected_cells(treatment, dose), seed=rng.randint(0, 10**9))
            cv2.imwrite(str(run_dir / "images" / f"{well_id}.png"), img)
            rows.append({"well_id": well_id, "sample_id": f"S-{rng.randint(10000, 99999)}",
                         "treatment": treatment, "dose_um": f"{dose:.3f}",
                         "image_file": f"images/{well_id}.png"})

    # Inject realistic faults so the validation layer has something to catch
    faults = ["bad_well_id", "missing_sample", "negative_dose", "duplicate_well", "missing_image"]
    for row in rng.sample(rows, k=int(len(rows) * fault_rate)):
        fault = rng.choice(faults)
        if fault == "bad_well_id":
            row["well_id"] = "I13"
        elif fault == "missing_sample":
            row["sample_id"] = ""
        elif fault == "negative_dose":
            row["dose_um"] = "-1.000"
        elif fault == "duplicate_well":
            rows.append(dict(row))
        elif fault == "missing_image":
            row["image_file"] = "images/DOES_NOT_EXIST.png"

    fieldnames = ["well_id", "sample_id", "treatment", "dose_um", "image_file"]
    if schema_break:  # upstream vendor renamed a column without telling anyone
        fieldnames[1] = "sampleID"
        for row in rows:
            row["sampleID"] = row.pop("sample_id")

    with open(run_dir / "wells.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # metadata.json is written LAST: it acts as the "run complete" marker
    meta = {"run_id": run_id, "plate_id": f"PLT-{rng.randint(1000, 9999)}",
            "instrument_id": "IMAGER-01", "operator": "sim-bot",
            "started_at": now.isoformat()}
    (run_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/incoming"))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--fault-rate", type=float, default=0.05)
    parser.add_argument("--schema-break", action="store_true")
    args = parser.parse_args()
    for _ in range(args.runs):
        print(generate_run(args.out, args.fault_rate, args.schema_break))


if __name__ == "__main__":
    main()
