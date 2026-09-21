"""
V2 migrations must leave the legacy/public schema completely untouched.
Representative legacy-style objects (including a public.alembic_version
decoy with V2's version-table name) are created in the DISPOSABLE test
database only; nothing here can reach a production database.
"""

import io

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from app.v2.db.metadata import metadata
from app.v2.db.scope import include_name, include_object
from app.v2.tests.db.harness import scalar, snapshot_non_v2, v2_objects

pytestmark = pytest.mark.db


def test_probe_snapshot_is_actually_sensitive(legacy_probe):
    """Guards the guard: the snapshot must notice legacy changes, or the tests below prove nothing."""
    from sqlalchemy import text
    before = snapshot_non_v2(legacy_probe)
    assert any(name == "legacy_probe_startups" for _, name, _ in before["objects"])
    for statement in (
        "INSERT INTO public.legacy_probe_startups (canonical_name, normalized_name) VALUES ('X','x')",
        "ALTER TABLE public.legacy_probe_startups ADD COLUMN extra int",
        "CREATE TABLE public.legacy_probe_extra (id int)",
        "UPDATE public.alembic_version SET version_num = 'changed'",
    ):
        with legacy_probe.begin() as conn:
            conn.execute(text(statement))
        assert snapshot_non_v2(legacy_probe) != before, statement
        with legacy_probe.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public.legacy_probe_extra"))
            conn.execute(text("ALTER TABLE public.legacy_probe_startups DROP COLUMN IF EXISTS extra"))
            conn.execute(text("DELETE FROM public.legacy_probe_startups WHERE normalized_name = 'x'"))
            conn.execute(text("UPDATE public.alembic_version SET version_num = 'legacy-decoy-not-v2'"))
        before = snapshot_non_v2(legacy_probe)


def test_upgrade_downgrade_upgrade_leave_legacy_untouched(legacy_probe, alembic_cfg):
    baseline = snapshot_non_v2(legacy_probe)

    command.upgrade(alembic_cfg(), "head")
    assert snapshot_non_v2(legacy_probe) == baseline

    command.downgrade(alembic_cfg(), "base")
    assert snapshot_non_v2(legacy_probe) == baseline

    command.upgrade(alembic_cfg(), "head")
    assert snapshot_non_v2(legacy_probe) == baseline


def test_public_alembic_version_decoy_is_untouched_and_separate_from_v2s(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    assert scalar(legacy_probe, "SELECT version_num FROM public.alembic_version") == "legacy-decoy-not-v2"
    assert scalar(legacy_probe, "SELECT version_num FROM v2.alembic_version") == "0001"
    command.downgrade(alembic_cfg(), "base")
    assert scalar(legacy_probe, "SELECT version_num FROM public.alembic_version") == "legacy-decoy-not-v2"


def test_v2_objects_exist_only_in_schema_v2(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(legacy_probe) == [("alembic_version", "r")]
    # nothing new anywhere else: covered by the full non-v2 snapshot equality above


def test_legacy_objects_created_after_v2_upgrade_are_also_untouched(clean_db, alembic_cfg):
    from app.v2.tests.db.harness import create_legacy_probe_objects
    command.upgrade(alembic_cfg(), "head")
    create_legacy_probe_objects(clean_db)
    baseline = snapshot_non_v2(clean_db)
    command.downgrade(alembic_cfg(), "base")
    command.upgrade(alembic_cfg(), "head")
    assert snapshot_non_v2(clean_db) == baseline


def test_alembic_check_ignores_legacy_tables(legacy_probe, alembic_cfg):
    """Runs the REAL env.py autogenerate path: legacy tables must not show up as drift."""
    command.upgrade(alembic_cfg(), "head")
    command.check(alembic_cfg())  # raises CommandError if autogenerate finds any difference


def _diff(engine, **kwargs):
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts=dict(target_metadata=metadata, include_schemas=True, version_table_schema="v2", **kwargs)
        )
        return compare_metadata(ctx, metadata)


def test_scope_filters_are_what_keep_legacy_out_of_autogenerate(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")

    unscoped = _diff(legacy_probe)  # negative control: same comparison WITHOUT V2's filters
    removed = {op[1].name for op in unscoped if op[0] == "remove_table"}
    assert {"legacy_probe_startups", "legacy_probe_analyses"} <= removed

    scoped = _diff(legacy_probe, include_name=include_name, include_object=include_object)
    assert scoped == []


def test_offline_sql_does_not_mention_legacy_objects(legacy_probe, alembic_cfg):
    cfg = alembic_cfg()
    cfg.output_buffer = io.StringIO()
    command.upgrade(cfg, "head", sql=True)
    sql = cfg.output_buffer.getvalue()
    assert "legacy_probe" not in sql and "public.alembic_version" not in sql
