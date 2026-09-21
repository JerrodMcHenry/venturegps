"""Deterministic fake proposers and helpers for the candidate-layer tests. No AI, no network, no database handle."""

from app.v2.domain.candidate import (
    CompanyCandidateProposal,
    EvidenceLocator,
    IdentifierType,
    ProposedIdentifier,
)
from app.v2.observations.hashing import compute_content_hash

PAGE = (
    "<html><body><h1>Acme Robotics, Inc.</h1>"
    "<p>Visit https://www.acmerobotics.com or ACMEROBOTICS.COM today. Also Globex Corporation.</p></body></html>"
).encode("utf-8")

MULTIBYTE = "Zürich — Acme Robotics, Inc. is based in Zürich.".encode("utf-8")

PROC, V1, V2 = "company_finder", "company_finder.v1", "company_finder.v2"


def locate(payload: bytes, needle: bytes, *, before: int = 0, after: int = 0, occurrence: int = 0) -> EvidenceLocator:
    """A locator for the `occurrence`-th appearance of `needle` in the exact payload bytes, optionally widened."""
    index = -1
    for _ in range(occurrence + 1):
        index = payload.index(needle, index + 1)
    start = max(0, index - before)
    end = min(len(payload), index + len(needle) + after)
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=compute_content_hash(payload[start:end]))


def make_proposal(payload: bytes, name: str, *, domain: str | None = None, url: str | None = None,
                  domain_needle: bytes | None = None, pad: int = 12) -> CompanyCandidateProposal:
    identifiers = []
    if domain is not None:
        identifiers.append(ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value=domain,
                                              evidence=locate(payload, domain_needle or domain.encode(), before=pad, after=pad)))
    if url is not None:
        identifiers.append(ProposedIdentifier(identifier_type=IdentifierType.WEBSITE_URL, value=url,
                                              evidence=locate(payload, url.encode(), before=pad, after=pad)))
    return CompanyCandidateProposal(proposed_name=name, name_evidence=locate(payload, name.encode(), before=pad, after=pad),
                                    identifiers=tuple(identifiers))


class FixedProposer:
    """Always proposes the same list, and records what it was handed."""

    def __init__(self, proposals):
        self._proposals = list(proposals)
        self.calls = []

    def propose(self, observation, payload):
        self.calls.append((observation, payload))
        return list(self._proposals)


class RaisingProposer:
    def __init__(self, exception):
        self._exception = exception

    def propose(self, observation, payload):
        raise self._exception


class ScriptedProposer:
    """Computes proposals from the payload it is given (a deterministic 'extractor')."""

    def __init__(self, fn):
        self._fn = fn

    def propose(self, observation, payload):
        return self._fn(observation, payload)
