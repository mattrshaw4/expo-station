-- Runs once, the first time the db-data volume is created.
CREATE TABLE IF NOT EXISTS tickets (
    id         BIGSERIAL PRIMARY KEY,
    dish       TEXT        NOT NULL,
    status     TEXT        NOT NULL DEFAULT 'fired',  -- fired | served | 86d
    fired_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    served_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS tickets_status_idx ON tickets (status);
