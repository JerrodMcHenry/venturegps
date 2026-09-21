"""
Deterministic evidence ingestion: bytes already supplied by a trusted collector
boundary -> RawPayload + Observation + ObservationSighting, atomically.

No network, no scheduling, no AI, no processing. Fetching and collectors are
later increments; this package only decides and persists.
"""
