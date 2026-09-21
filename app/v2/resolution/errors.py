"""Typed refusals of the resolution boundary. Static messages; never a value from the data."""

from app.v2.repositories.errors import ConflictError


class CandidateAlreadyResolvedError(ConflictError):
    """The candidate already has a final decision; it cannot be resolved twice."""


class IdentifierConflictError(ConflictError):
    """A canonical identifier already belongs to a different Company. There is no auto-merge."""
