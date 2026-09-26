"""Load validated data into PostgreSQL. Every write is an upsert inside one transaction."""
import os

import psycopg2
from psycopg2.extras import Json, execute_values

DEFAULT_DB_URL = "postgresql://labflow:labflow@localhost:5432/labflow"


def get_conn():
    return psycopg2.connect(os.environ.get("LABFLOW_DB_URL", DEFAULT_DB_URL))


def load_run(conn, meta: dict, valid: list[dict], rejected: list[dict]) -> None:
    run_id = meta["run_id"]
    with conn:                      # one transaction: all of it saves, or none of it does
        with conn.cursor() as cur:
            # 1. Save the plate info (insert, or update if it's already there)
            cur.execute("""
                INSERT INTO plate_runs (run_id, plate_id, instrument_id, operator, started_at)
                VALUES (%(run_id)s, %(plate_id)s, %(instrument_id)s, %(operator)s, %(started_at)s)
                ON CONFLICT (run_id) DO UPDATE SET
                    plate_id = EXCLUDED.plate_id,
                    instrument_id = EXCLUDED.instrument_id,
                    operator = EXCLUDED.operator,
                    started_at = EXCLUDED.started_at,
                    loaded_at = now()
            """, {**meta, "operator": meta.get("operator")})

            # 2. Save all good wells in one batch
            execute_values(cur, """
                INSERT INTO wells (run_id, well_id, sample_id, treatment, dose_um, image_path)
                VALUES %s
                ON CONFLICT (run_id, well_id) DO UPDATE SET
                    sample_id = EXCLUDED.sample_id,
                    treatment = EXCLUDED.treatment,
                    dose_um = EXCLUDED.dose_um,
                    image_path = EXCLUDED.image_path
            """, [(run_id, w["well_id"], w["sample_id"], w["treatment"], w["dose_um"],
                   w["image_path"]) for w in valid])

            # 3. Replace this run's quarantined rows
            cur.execute("DELETE FROM rejected_records WHERE run_id = %s", (run_id,))
            if rejected:
                execute_values(cur, """
                    INSERT INTO rejected_records (run_id, source_file, row_number, raw_record, reason)
                    VALUES %s
                """, [(run_id, "wells.csv", r["row_number"], Json(r["raw"]), r["reason"])
                      for r in rejected])
