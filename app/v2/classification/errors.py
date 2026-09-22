"""Typed refusals of the classification boundary. Static messages; never a value from the data."""

from app.v2.repositories.errors import ConflictError


class AlreadyClassifiedError(ConflictError):
    """This exact (Company, Market, taxonomy version) is already classified. There is no silent re-classification."""


class PrimaryAlreadyAssignedError(ConflictError):
    """The Company already has a PRIMARY classification under this taxonomy version. There can only be one."""
