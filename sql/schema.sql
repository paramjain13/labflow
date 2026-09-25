-- One row per plate run
CREATE TABLE IF NOT EXISTS plate_runs (
    run_id        TEXT PRIMARY KEY,
    plate_id      TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    operator      TEXT,
    started_at    TIMESTAMPTZ NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    eln_entry_id  TEXT                  -- filled in later, in the ELN lesson
);

-- One row per well (96 per plate)
CREATE TABLE IF NOT EXISTS wells (
    run_id     TEXT NOT NULL REFERENCES plate_runs(run_id) ON DELETE CASCADE,
    well_id    TEXT NOT NULL CHECK (well_id ~ '^[A-H](0[1-9]|1[0-2])$'),
    sample_id  TEXT NOT NULL,
    treatment  TEXT NOT NULL,
    dose_um    NUMERIC(8,3) NOT NULL CHECK (dose_um >= 0),
    image_path TEXT NOT NULL,
    PRIMARY KEY (run_id, well_id)
);

-- The quarantine pile: bad rows, exactly as received, plus the reason
CREATE TABLE IF NOT EXISTS rejected_records (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id      TEXT,
    source_file TEXT NOT NULL,
    row_number  INTEGER,
    raw_record  JSONB,
    reason      TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
