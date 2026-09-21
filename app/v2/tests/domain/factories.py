from datetime import datetime, timezone

from app.v2.domain.content import MediaType
from app.v2.domain.observation import Observation

GOOD_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # sha256 of b""
OBSERVED = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def observation_kwargs(**overrides):
    base = dict(
        source_key="sec_edgar",
        observation_type="filing_document",
        observed_time=OBSERVED,
        collection_version="manual_upload.v1",
        collector_id="admin:user_2abc",
        content_hash=GOOD_HASH,
        sniffed_media_type=MediaType.TEXT_PLAIN,
    )
    base.update(overrides)
    return base


def make_observation(**overrides) -> Observation:
    return Observation(**observation_kwargs(**overrides))
