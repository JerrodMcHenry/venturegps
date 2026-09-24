"""Typed refusals of the lifecycle resolution boundary. Static messages; never a value from the data."""

from app.v2.repositories.errors import ConflictError


class LifecycleCandidateAlreadyResolvedError(ConflictError):
    """The candidate already has a final decision; it cannot be resolved twice."""


class FactAlreadyAcceptedError(ConflictError):
    """This exact candidate fact was already accepted onto the company. Never silently overwritten; a
    correction is a NEW candidate and a NEW accepted fact, not a rewrite of this one."""


class FactNotAvailableError(ConflictError):
    """The selected fact was not proposed (with evidence) on the resolved candidate."""
