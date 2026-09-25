import csv
import json

import pytest

from labflow.validate import (SchemaError, ValidationResult, check_rejection_rate,
                              load_metadata, validate_wells)

GOOD = {"well_id": "A01", "sample_id": "S-1", "treatment": "DMSO",
        "dose_um": "0", "image_file": "images/A01.png"}
COLUMNS = ["well_id", "sample_id", "treatment", "dose_um", "image_file"]


def make_run(tmp_path, rows, fieldnames=COLUMNS):
    """Build a tiny fake run folder for testing."""
    run = tmp_path / "RUN_TEST"
    (run / "images").mkdir(parents=True)
    (run / "images" / "A01.png").write_bytes(b"")
    with open(run / "wells.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (run / "metadata.json").write_text(json.dumps({
        "run_id": "RUN_TEST", "plate_id": "P1", "instrument_id": "I1",
        "started_at": "2026-09-25T10:00:00+00:00"}))
    return run


def test_bad_rows_are_quarantined(tmp_path):
    rows = [GOOD, dict(GOOD), dict(GOOD, well_id="Z99"), dict(GOOD, well_id="A02", dose_um="-1")]
    result = validate_wells(make_run(tmp_path, rows))
    assert len(result.valid) == 1
    reasons = sorted(r["reason"].split(":")[0] for r in result.rejected)
    assert reasons == ["bad_well_id", "duplicate_well", "negative_dose"]


def test_renamed_column_fails_loudly(tmp_path):
    cols = ["well_id", "sampleID", "treatment", "dose_um", "image_file"]
    row = {"well_id": "A01", "sampleID": "S-1", "treatment": "DMSO",
           "dose_um": "0", "image_file": "images/A01.png"}
    with pytest.raises(SchemaError, match="sample_id"):
        validate_wells(make_run(tmp_path, [row], cols))


def test_misfiled_run_fails(tmp_path):
    run = make_run(tmp_path, [GOOD])
    meta = json.loads((run / "metadata.json").read_text())
    meta["run_id"] = "SOMETHING_ELSE"
    (run / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(SchemaError, match="does not match folder"):
        load_metadata(run)


def test_circuit_breaker():
    check_rejection_rate(ValidationResult(valid=[{}] * 9, rejected=[{}] * 1))   # 10%: OK
    with pytest.raises(SchemaError, match="exceeds"):
        check_rejection_rate(ValidationResult(valid=[{}] * 7, rejected=[{}] * 3))  # 30%: stop
