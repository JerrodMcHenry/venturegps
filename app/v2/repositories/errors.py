"""Typed persistence errors. Static messages only; never a value from the data."""

from app.v2.domain.errors import DomainError


class NotFoundError(DomainError):
    """The requested record does not exist."""


class ConflictError(DomainError):
    """The request conflicts with what is already stored."""
