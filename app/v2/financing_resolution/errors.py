"""Typed refusals of the financing resolution boundary. Static messages; never a value from the data."""

from app.v2.repositories.errors import ConflictError


class FinancingCandidateAlreadyResolvedError(ConflictError):
    """The candidate already has a final decision; it cannot be resolved twice."""


class WrongCompanyError(ConflictError):
    """The candidate concerns a different Company than the target event. There is no cross-company attach."""


class FactAlreadyAcceptedError(ConflictError):
    """The event already holds a canonical value for this fact. It is never silently overwritten."""


class FactNotAvailableError(ConflictError):
    """The selected fact was not proposed (with evidence) on the resolved candidate."""
