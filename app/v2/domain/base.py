"""Shared base for immutable V2 domain models."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Frozen, strict, closed (extra fields forbidden) and input-hiding.

    strict=True: no silent coercion (a str is not a datetime, a str is not an
    enum member). hide_input_in_errors=True: validation errors never echo the
    offending value, which may be untrusted source content.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)
