"""
Pure-domain tests run with the network blocked (autouse) and can opt into an
environment tripwire. Nothing in app.v2.domain / app.v2.observations should ever
need either.
"""

import os
import socket
from contextlib import contextmanager

import pytest


def _network_attempted(*_args, **_kwargs):
    raise AssertionError("network access attempted by a pure-domain test")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _network_attempted)
    monkeypatch.setattr(socket.socket, "connect_ex", _network_attempted)
    monkeypatch.setattr(socket, "create_connection", _network_attempted)
    monkeypatch.setattr(socket, "getaddrinfo", _network_attempted)
    monkeypatch.setattr(socket, "gethostbyname", _network_attempted)


class _EnvironmentTripwire:
    def _hit(self, *_a, **_k):
        raise AssertionError("environment variable read by pure code")

    __getitem__ = get = __contains__ = __iter__ = __len__ = keys = values = items = copy = _hit


@contextmanager
def _tripwire_active():
    original = os.environ
    os.environ = _EnvironmentTripwire()
    try:
        yield
    finally:
        os.environ = original  # restored before pytest formats any failure


@pytest.fixture
def env_tripwire():
    """Use as `with env_tripwire():` -- any read of os.environ / os.getenv inside raises.
    Scoped to the with-block so pytest's own reporting can never trip it."""
    return _tripwire_active
