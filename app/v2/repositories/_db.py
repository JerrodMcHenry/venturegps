"""Plumbing shared by the V2 repositories: transaction handling and error translation."""

from contextlib import contextmanager

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.domain.errors import InvariantViolationError


@contextmanager
def connection(db: Engine | Connection):
    """An Engine runs the operation in its own transaction; a Connection joins the caller's."""
    if isinstance(db, Engine):
        with db.begin() as conn:
            yield conn
    else:
        yield db


def constraint_of(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def integrity_error_to_domain(exc: IntegrityError) -> InvariantViolationError:
    """The detail is our own constraint/trigger name or message, never a data value."""
    diag = getattr(exc.orig, "diag", None)
    detail = (getattr(diag, "constraint_name", None) or getattr(diag, "message_primary", None)
              or "constraint violated")
    return InvariantViolationError("persistence_constraint_violation", f"database rejected the change: {detail}")


@contextmanager
def translating_integrity_errors():
    """Unexpected database rejections become InvariantViolationError."""
    try:
        yield
    except IntegrityError as exc:
        raise integrity_error_to_domain(exc) from None
