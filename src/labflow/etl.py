"""Run the pipeline for one plate run: Extract -> Validate -> Load."""
import sys
from contextlib import closing
from pathlib import Path

from labflow.load import get_conn, load_run
from labflow.validate import check_rejection_rate, load_metadata, validate_wells


def run(run_dir: Path) -> None:
    meta = load_metadata(run_dir)
    result = validate_wells(run_dir)
    check_rejection_rate(result)
    with closing(get_conn()) as conn:
        load_run(conn, meta, result.valid, result.rejected)
    print(f"{meta['run_id']}: loaded {len(result.valid)} wells, quarantined {len(result.rejected)}")


if __name__ == "__main__":
    run(Path(sys.argv[1]))
