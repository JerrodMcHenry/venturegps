"""
Typed domain validation errors.

Three kinds, each with a stable machine-readable `code`:

- InvalidInputError       the value is malformed or breaks a rule for its type
- UnsupportedInputError   well-formed, but outside what V2 supports (e.g. a URL scheme)
- InvariantViolationError a state/logic rule was broken (e.g. an illegal state transition)

Messages are STATIC text chosen by this codebase. They must never embed the
offending value: values come from external sources and may contain raw
payload content or secrets. Models built on app.v2.domain.base.DomainModel
also hide input values in pydantic errors.

Rule violations raised inside model validators propagate as these types;
purely structural problems (missing/extra/wrong-typed fields) surface as
pydantic.ValidationError, which as_domain_error() converts.
"""

from pydantic import ValidationError


class DomainError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class InvalidInputError(DomainError):
    pass


class UnsupportedInputError(DomainError):
    pass


class InvariantViolationError(DomainError):
    pass


def as_domain_error(exc: ValidationError) -> InvalidInputError:
    """Convert a structural pydantic error into InvalidInputError, keeping only
    field paths and error kinds -- never input values, and never the names of
    unexpected extra keys (those come from the caller's data)."""
    parts = set()
    for error in exc.errors(include_input=False, include_url=False, include_context=False):
        if error["type"] == "extra_forbidden":
            parts.add("unexpected field")
        else:
            parts.add(f"{'.'.join(str(p) for p in error['loc'])} ({error['type']})")
    return InvalidInputError("invalid_structure", "invalid structure: " + "; ".join(sorted(parts)))
