"""Create v2.observation_sighting

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-21

Acquisition history: "on these occasions VentureGPS saw this Observation".

A sighting stores only what is specific to the acquisition (when, by whom,
under which collection version, under which acquisition key). It never
copies payload bytes or Source fields, and carries no processing state, AI
field or interpretation.

Identity / idempotency: UNIQUE (observation_id, acquisition_key). The key
identifies one acquisition event and is supplied by the collector boundary. It
is unique per Observation (not globally) so one collection run may reuse a
single key across many records, while the same Observation seen at 10:00 and
at 11:00 (two keys) yields two sightings and a replay of the 10:00 command
yields none. Neither observation_id nor (observation_id, observed_time) is
unique: repeated checks are legitimate.

Append-only and DB-assigned recorded_time REUSE the 0003 functions
(v2.forbid_evidence_change, v2.observation_stamp): both are table-agnostic
(the first names the table it is protecting via TG_TABLE_NAME; the second
sets NEW.recorded_time). No new function is needed.

Downgrade removes only this table and REFUSES to run while it holds rows.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

CREATE_TABLE = """
CREATE TABLE v2.observation_sighting (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY,
    observation_id     BIGINT      NOT NULL,
    observed_time      TIMESTAMPTZ NOT NULL,
    recorded_time      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    collector_id       TEXT        NOT NULL,
    collection_version TEXT        NOT NULL,
    acquisition_key    TEXT        NOT NULL,
    CONSTRAINT pk_observation_sighting PRIMARY KEY (id),
    CONSTRAINT fk_observation_sighting_observation_id_observation
        FOREIGN KEY (observation_id) REFERENCES v2.observation (id) ON DELETE RESTRICT,
    CONSTRAINT uq_observation_sighting_acquisition UNIQUE (observation_id, acquisition_key),
    CONSTRAINT ck_observation_sighting_collector_id_shape
        CHECK (collector_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$'),
    CONSTRAINT ck_observation_sighting_collection_version_shape
        CHECK (collection_version ~ '^[a-z][a-z0-9_]{0,63}\\.v[1-9][0-9]{0,5}$'),
    CONSTRAINT ck_observation_sighting_acquisition_key_shape
        CHECK (acquisition_key ~ '^[A-Za-z0-9][A-Za-z0-9_.:@/=+-]{0,127}$')
)
"""

CREATE_TRIGGERS = """
CREATE TRIGGER trg_observation_sighting_append_only
    BEFORE UPDATE OR DELETE ON v2.observation_sighting
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_observation_sighting_no_truncate
    BEFORE TRUNCATE ON v2.observation_sighting
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_observation_sighting_stamp
    BEFORE INSERT ON v2.observation_sighting
    FOR EACH ROW EXECUTE FUNCTION v2.observation_stamp()
"""

REFUSE_IF_SIGHTINGS_EXIST = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.observation_sighting) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0004: v2.observation_sighting contains evidence',
            HINT = 'Sightings are append-only. Back them up and drop the table by hand if you truly mean to discard them.',
            ERRCODE = 'restrict_violation';
    END IF;
END
$$
"""


def upgrade() -> None:
    op.execute(sa.text(CREATE_TABLE))
    for statement in CREATE_TRIGGERS.split(";\n"):
        if statement.strip():
            op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_SIGHTINGS_EXIST))
    op.execute("DROP TABLE v2.observation_sighting")  # drops its triggers and identity sequence too
