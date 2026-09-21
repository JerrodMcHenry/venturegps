"""The test-database safety rule itself (no database needed). See guard.py for the rule."""

import pytest

from app.v2.tests.db.guard import (
    DISPOSABLE_MARKER,
    DatabaseNotConfigured,
    UnsafeTestDatabaseError,
    validate_test_database_url,
    verify_server_attests_disposable,
)

GOOD = "postgresql://u:s3cret@127.0.0.1:54329/venturegps_v2_test"


def unsafe(raw, **kwargs):
    with pytest.raises(UnsafeTestDatabaseError) as info:
        validate_test_database_url(raw, **kwargs)
    return str(info.value)


@pytest.mark.parametrize(
    "raw, host, database",
    [
        (GOOD, "127.0.0.1", "venturegps_v2_test"),
        ("postgresql+psycopg2://u@localhost/venturegps_v2_test", "localhost", "venturegps_v2_test"),
        ("postgresql://u@localhost:5433/venturegps_v2_test_w1", "localhost", "venturegps_v2_test_w1"),
        ("postgresql://u@[::1]:5432/venturegps_v2_test", "::1", "venturegps_v2_test"),
        ("postgresql://u@/venturegps_v2_test?host=/var/run/postgresql", "/var/run/postgresql", "venturegps_v2_test"),
        ("  " + GOOD + "  ", "127.0.0.1", "venturegps_v2_test"),
    ],
)
def test_safe_targets_are_accepted(raw, host, database):
    target = validate_test_database_url(raw)
    assert (target.host, target.database) == (host, database)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unset_is_reported_as_not_configured_not_unsafe(raw):
    with pytest.raises(DatabaseNotConfigured):
        validate_test_database_url(raw)


@pytest.mark.parametrize(
    "database",
    [
        "postgres", "venturegps", "sie_staging", "venturegps_v2", "test", "v2_test",
        "venturegps_v2_testing", "VENTUREGPS_V2_TEST", "prod_venturegps_v2_test",
        "venturegps_v2_test_", "venturegps_v2_test-x", "venturegps_v2_test_a_b",
        "venturegps_v2_test_A", "venturegps_v2_test%20",
    ],
)
def test_database_name_must_match_the_test_convention_even_on_localhost(database):
    assert "does not match" in unsafe(f"postgresql://u@127.0.0.1:5432/{database}")


def test_localhost_alone_is_not_sufficient():
    assert "does not match" in unsafe("postgresql://localhost/postgres")
    assert "does not match" in unsafe("postgresql://localhost/sie_staging")


def test_missing_database_name_is_refused():
    assert "does not match" in unsafe("postgresql://u@127.0.0.1:5432/")
    assert "does not match" in unsafe("postgresql://u@127.0.0.1:5432")


@pytest.mark.parametrize("raw", ["sqlite:///venturegps_v2_test", "mysql://u@localhost/venturegps_v2_test", "http://localhost/venturegps_v2_test"])
def test_non_postgres_drivers_are_refused(raw):
    assert "unsupported driver" in unsafe(raw)


def test_unparseable_url_is_refused():
    assert "could not be parsed" in unsafe("not a url")


def test_remote_host_needs_an_explicit_opt_in_even_with_a_valid_name():
    remote = "postgresql://u:p@dpg-abc123.oregon-postgres.render.com/venturegps_v2_test"
    assert "not loopback" in unsafe(remote)
    assert "not loopback" in unsafe(remote, allowed_hosts=["other.example.com"])
    assert validate_test_database_url(remote, allowed_hosts=["DPG-abc123.oregon-postgres.render.com"]).database == "venturegps_v2_test"


def test_missing_host_is_refused():
    assert "host must be explicit" in unsafe("postgresql:///venturegps_v2_test")


def test_allowed_hosts_never_bypass_the_database_name_rule():
    assert "does not match" in unsafe("postgresql://u@db.example.com/prod", allowed_hosts=["db.example.com"])


@pytest.mark.parametrize("env_name", ["DATABASE_URL", "V2_DATABASE_URL"])
def test_same_database_name_as_production_is_refused_on_any_host(env_name):
    prod = {env_name: "postgres://app:pw@db.internal:5432/venturegps_v2_test"}
    assert env_name in unsafe(GOOD, production_urls=prod)
    assert env_name in unsafe("postgresql://u@localhost/venturegps_v2_test", production_urls=prod)


def test_unrelated_or_garbage_production_urls_do_not_block_or_crash():
    ok = validate_test_database_url(GOOD, production_urls={"DATABASE_URL": "postgresql://a@h/sie_prod", "V2_DATABASE_URL": "%%%not-a-url"})
    assert ok.database == "venturegps_v2_test"


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://u:s3cret@127.0.0.1/prod_db",
        "postgresql://u:s3cret@evil.example.com/venturegps_v2_test",
        "mysql://u:s3cret@localhost/venturegps_v2_test",
        "postgresql://u:s3cret@[bad/venturegps_v2_test",
    ],
)
def test_error_messages_never_leak_the_password(raw):
    assert "s3cret" not in unsafe(raw)


# ---- server-side attestation (fake connection; the real one is exercised by the DB tests)

class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeConnection:
    def __init__(self, current, marker):
        self._answers = [current, marker]

    def execute(self, *_args, **_kwargs):
        return _Result(self._answers.pop(0))


def _target(database="venturegps_v2_test"):
    return validate_test_database_url(f"postgresql://u@127.0.0.1/{database}")


def test_server_attestation_passes_only_with_the_exact_marker_and_name():
    verify_server_attests_disposable(_FakeConnection("venturegps_v2_test", DISPOSABLE_MARKER), _target())


@pytest.mark.parametrize("marker", [None, "", "production", DISPOSABLE_MARKER.lower(), DISPOSABLE_MARKER + " "])
def test_server_attestation_refuses_an_unmarked_database(marker):
    with pytest.raises(UnsafeTestDatabaseError, match="not marked disposable"):
        verify_server_attests_disposable(_FakeConnection("venturegps_v2_test", marker), _target())


def test_server_attestation_refuses_when_connected_to_a_different_database():
    with pytest.raises(UnsafeTestDatabaseError, match="connected to"):
        verify_server_attests_disposable(_FakeConnection("sie_prod", DISPOSABLE_MARKER), _target())
