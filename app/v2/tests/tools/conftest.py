"""
app.v2.tools's parsing/proposer modules (form_d_xml, form_d_company_proposer, form_d_financing_proposer,
manual_fact) take only bytes and immutable domain objects and must never touch the network -- same guarantee
app/v2/tests/domain/conftest.py enforces for app.v2.domain/app.v2.observations, reused here for the same reason.
"""

import socket

import pytest


def _network_attempted(*_args, **_kwargs):
    raise AssertionError("network access attempted by an app.v2.tools parsing/proposer test")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _network_attempted)
    monkeypatch.setattr(socket.socket, "connect_ex", _network_attempted)
    monkeypatch.setattr(socket, "create_connection", _network_attempted)
    monkeypatch.setattr(socket, "getaddrinfo", _network_attempted)
    monkeypatch.setattr(socket, "gethostbyname", _network_attempted)
