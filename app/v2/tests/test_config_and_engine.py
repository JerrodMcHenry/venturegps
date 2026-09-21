"""V2 config and engine factory: lazy, explicit, small pool, no test-URL fallback."""

import pytest
from sqlalchemy.pool import NullPool

from app.v2 import config
from app.v2.db import engine as engine_module


def test_database_url_prefers_v2_then_falls_back_to_database_url():
    assert config.get_database_url({"V2_DATABASE_URL": "postgresql://a@h/one", "DATABASE_URL": "postgresql://a@h/two"}).endswith("/one")
    assert config.get_database_url({"DATABASE_URL": "postgresql://a@h/two"}).endswith("/two")


def test_missing_configuration_is_an_error_not_a_default():
    with pytest.raises(config.ConfigurationError, match="no database configured"):
        config.get_database_url({})
    with pytest.raises(config.ConfigurationError):
        config.get_database_url({"DATABASE_URL": "   "})


def test_config_never_reads_the_test_database_url():
    with pytest.raises(config.ConfigurationError):
        config.get_database_url({"V2_TEST_DATABASE_URL": "postgresql://a@h/venturegps_v2_test"})
    assert config.get_database_url(
        {"V2_TEST_DATABASE_URL": "postgresql://a@h/venturegps_v2_test", "DATABASE_URL": "postgresql://a@h/prod"}
    ).endswith("/prod")


def test_render_style_scheme_is_normalized_and_other_drivers_rejected():
    assert config.normalize_database_url("postgres://u:p@h/db") == "postgresql://u:p@h/db"
    for bad in ("sqlite:///x.db", "mysql://u@h/db", "", "garbage"):
        with pytest.raises(config.ConfigurationError) as info:
            config.normalize_database_url(bad)
        assert bad not in str(info.value) or bad == ""


def test_config_errors_never_contain_the_url():
    with pytest.raises(config.ConfigurationError) as info:
        config.normalize_database_url("mysql://user:s3cret@host/db")
    assert "s3cret" not in str(info.value)


def test_redaction_hides_credentials():
    assert config.redact_database_url("postgresql://user:s3cret@db.example.com:5432/app") == "db.example.com:5432/app"


def test_migration_lock_timeout_parsing():
    assert config.get_migration_lock_timeout({}) == config.DEFAULT_MIGRATION_LOCK_TIMEOUT_SECONDS
    assert config.get_migration_lock_timeout({"V2_MIGRATION_LOCK_TIMEOUT_SECONDS": "2.5"}) == 2.5
    for bad in ("abc", "-1"):
        with pytest.raises(config.ConfigurationError):
            config.get_migration_lock_timeout({"V2_MIGRATION_LOCK_TIMEOUT_SECONDS": bad})


def test_make_engine_is_small_pooled_and_labelled_and_does_not_connect(monkeypatch):
    captured = {}
    monkeypatch.setattr(engine_module, "create_engine", lambda url, **kw: captured.update(url=url, **kw) or object())
    engine_module.make_engine("postgres://u:p@h/db")
    assert captured["url"] == "postgresql://u:p@h/db"
    assert captured["pool_size"] == 2 and captured["max_overflow"] == 2
    assert captured["pool_pre_ping"] is True
    assert captured["connect_args"] == {"application_name": "venturegps-v2"}


def test_unpooled_engine_uses_nullpool():
    engine = engine_module.make_engine("postgresql://u:p@127.0.0.1:1/db", pooled=False)  # dead port: creation must not connect
    assert isinstance(engine.pool, NullPool)
    engine.dispose()


def test_pooled_engine_creation_does_not_connect():
    engine = engine_module.make_engine("postgresql://u:p@127.0.0.1:1/db")
    assert engine.pool.size() == 2
    engine.dispose()


def test_get_engine_is_lazy_cached_and_disposable(monkeypatch):
    built = []

    class FakeEngine:
        disposed = False
        def dispose(self):
            self.disposed = True

    monkeypatch.setattr(engine_module, "make_engine", lambda url, **kw: built.append(url) or FakeEngine())
    monkeypatch.setenv("V2_DATABASE_URL", "postgresql://u:p@h/db")
    engine_module.dispose_engine()
    assert built == []
    first = engine_module.get_engine()
    assert engine_module.get_engine() is first and len(built) == 1
    engine_module.dispose_engine()
    assert first.disposed
    assert engine_module.get_engine() is not first
    engine_module.dispose_engine()
