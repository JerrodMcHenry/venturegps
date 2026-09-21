"""
ObservationSighting: WHEN VentureGPS acquired (saw) an Observation.

An Observation says "this Source exposed this evidence record". A Sighting says
"we looked, and saw it". They are different facts, and only the second one
distinguishes "we checked and saw the same evidence again" from "we did not
check", which later coverage measurement depends on.

Temporal semantics (also see app.v2.domain.time):

  Observation.observed_time  the FIRST time VentureGPS observed this exact
                             Observation identity. Set once, never rewritten.
  Sighting.observed_time     EACH acquisition time, including the first one.
  recorded_time              when the database persisted it; never caller-supplied.

A repeat acquisition of identical evidence creates another Sighting; it never
mutates the Observation, its observed_time, or the payload. Sightings may
arrive out of order (a delayed collector): a Sighting's observed_time may be
earlier than the Observation's, and that is recorded as-is.

Idempotency: `acquisition_key` identifies one acquisition EVENT and is chosen
by the collector boundary (for example derived from its run and fetch
identity), never generated randomly inside a retry. Within one Observation a
key is used at most once, so replaying the same ingestion command does not
create a duplicate, while a later check of the same evidence (a new key) does.
"""

import re
from typing import Annotated

from pydantic import AfterValidator, Field

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.observation import CollectorId
from app.v2.domain.time import UtcDatetime
from app.v2.domain.versions import VersionId

_ACQUISITION_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/=+-]{0,127}")


def validate_acquisition_key(value: object) -> str:
    if not isinstance(value, str) or _ACQUISITION_KEY.fullmatch(value) is None:
        raise InvalidInputError("invalid_acquisition_key", "acquisition key must be 1-128 characters from A-Za-z0-9_.:@/=+-")
    return value


AcquisitionKey = Annotated[str, AfterValidator(validate_acquisition_key)]


class Sighting(DomainModel):
    observed_time: UtcDatetime
    collector_id: CollectorId
    collection_version: VersionId
    acquisition_key: AcquisitionKey


class StoredSighting(DomainModel):
    """A Sighting as persisted. Sightings are append-only evidence: no updated_time."""

    id: int = Field(gt=0)
    observation_id: int = Field(gt=0)
    sighting: Sighting
    recorded_time: UtcDatetime
