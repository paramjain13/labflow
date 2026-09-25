"""Data-quality layer: fail loudly on structural problems, quarantine bad rows."""
import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REQUIRED_META = {"run_id", "plate_id", "instrument_id", "started_at"}
REQUIRED_COLUMNS = {"well_id", "sample_id", "treatment", "dose_um", "image_file"}
ALLOWED_TREATMENTS = {"DMSO", "CompoundA", "CompoundB", "CompoundC"}
WELL_RE = re.compile(r"^[A-H](0[1-9]|1[0-2])$")


class SchemaError(Exception):
    """Structural problem with a whole file. The pipeline must stop."""


@dataclass
class ValidationResult:
    valid: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        total = len(self.valid) + len(self.rejected)
        return len(self.rejected) / total if total else 0.0


def load_metadata(run_dir: Path) -> dict:
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        raise SchemaError(f"{run_dir.name}: metadata.json missing (run incomplete?)")
    meta = json.loads(meta_path.read_text())
    missing = REQUIRED_META - meta.keys()
    if missing:
        raise SchemaError(f"{run_dir.name}: metadata missing fields {sorted(missing)}")
    if meta["run_id"] != run_dir.name:
        raise SchemaError(f"run_id {meta['run_id']} does not match folder {run_dir.name}")
    try:
        datetime.fromisoformat(meta["started_at"])
    except ValueError as exc:
        raise SchemaError(f"{run_dir.name}: bad started_at {meta['started_at']!r}") from exc
    return meta


def _check_row(row: dict, run_dir: Path, seen: set[str]) -> str | None:
    """Return a 'category: detail' reason if the row is bad, else None."""
    if not WELL_RE.match(row["well_id"] or ""):
        return f"bad_well_id: {row['well_id']!r}"
    if row["well_id"] in seen:
        return f"duplicate_well: {row['well_id']}"
    if not (row["sample_id"] or "").strip():
        return "missing_sample: empty sample_id"
    if row["treatment"] not in ALLOWED_TREATMENTS:
        return f"unknown_treatment: {row['treatment']!r}"
    try:
        dose = float(row["dose_um"])
    except (TypeError, ValueError):
        return f"bad_dose: {row['dose_um']!r}"
    if dose < 0:
        return f"negative_dose: {dose}"
    if not (run_dir / row["image_file"]).exists():
        return f"missing_image: {row['image_file']}"
    return None


def validate_wells(run_dir: Path) -> ValidationResult:
    csv_path = run_dir / "wells.csv"
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise SchemaError(f"{run_dir.name}/wells.csv missing columns {sorted(missing)}; "
                              f"got {reader.fieldnames}")
        result, seen = ValidationResult(), set()
        for line_no, row in enumerate(reader, start=2):
            reason = _check_row(row, run_dir, seen)
            if reason:
                result.rejected.append({"row_number": line_no, "raw": row, "reason": reason})
                continue
            seen.add(row["well_id"])
            result.valid.append({
                "well_id": row["well_id"],
                "sample_id": row["sample_id"].strip(),
                "treatment": row["treatment"],
                "dose_um": float(row["dose_um"]),
                "image_path": str(run_dir / row["image_file"]),
            })
    return result


def check_rejection_rate(result: ValidationResult, max_rate: float = 0.20) -> None:
    """Circuit breaker: a few bad rows is normal; lots of bad rows means something upstream broke."""
    if result.rejection_rate > max_rate:
        raise SchemaError(f"rejection rate {result.rejection_rate:.0%} exceeds {max_rate:.0%}")
