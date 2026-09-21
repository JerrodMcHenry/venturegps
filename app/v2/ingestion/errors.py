"""Ingestion-policy errors (static messages; never a value from the evidence)."""

from app.v2.domain.errors import DomainError


class SourceInactiveError(DomainError):
    """The Source is registered but deactivated, so new evidence is not ingested.
    This is an ingestion POLICY, not historical truth: existing evidence is untouched."""
