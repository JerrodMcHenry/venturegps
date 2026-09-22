"""
Table definitions for V2-owned tables, registered on app.v2.db.metadata.metadata.

These describe the SHAPE for queries and for Alembic's drift check. The
migrations are the source of truth for constraints and triggers: CHECK
constraints and the v2.source guard trigger live in the migration SQL only,
so there is one definition of each, not two that can drift.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)

from app.v2.db.metadata import metadata

# Revision 0002.
source_table = Table(
    "source",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("source_key", Text, nullable=False),
    Column("source_name", Text, nullable=False),
    Column("source_type", Text, nullable=False),
    Column("collection_method", Text, nullable=False),
    Column("source_url", Text, nullable=True),
    Column("is_active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("source_key"),
)

# Revision 0003: immutable evidence (append-only; enforced by triggers in the migration).
raw_payload_table = Table(
    "raw_payload",
    metadata,
    Column("content_hash", Text, primary_key=True),
    Column("storage_kind", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("payload_bytes", LargeBinary, nullable=True),
)

observation_table = Table(
    "observation",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("source_id", BigInteger, ForeignKey("v2.source.id", ondelete="RESTRICT"), nullable=False),
    Column("source_record_identifier", Text, nullable=True),
    Column("observation_type", Text, nullable=False),
    Column("event_time", DateTime(timezone=True), nullable=True),
    Column("event_time_precision", Text, nullable=True),
    Column("observed_time", DateTime(timezone=True), nullable=False),
    Column("recorded_time", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    Column("collection_version", Text, nullable=False),
    Column("collector_id", Text, nullable=False),
    Column("content_hash", Text, ForeignKey("v2.raw_payload.content_hash", ondelete="RESTRICT"), nullable=False),
    Column("declared_media_type", Text, nullable=True),
    Column("sniffed_media_type", Text, nullable=False),
    # Dedup identity: same source + same record identity (including "none") + same exact bytes.
    Index("uq_observation_dedup_with_record_id", "source_id", "source_record_identifier", "content_hash",
          unique=True, postgresql_where=text("source_record_identifier IS NOT NULL")),
    Index("uq_observation_dedup_without_record_id", "source_id", "content_hash",
          unique=True, postgresql_where=text("source_record_identifier IS NULL")),
)

# Revision 0004: acquisition history (append-only; enforced by triggers in the migration).
observation_sighting_table = Table(
    "observation_sighting",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("observation_id", BigInteger, ForeignKey("v2.observation.id", ondelete="RESTRICT"), nullable=False),
    Column("observed_time", DateTime(timezone=True), nullable=False),
    Column("recorded_time", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    Column("collector_id", Text, nullable=False),
    Column("collection_version", Text, nullable=False),
    Column("acquisition_key", Text, nullable=False),
    UniqueConstraint("observation_id", "acquisition_key", name="uq_observation_sighting_acquisition"),
)

# Revision 0005: processing history (mutable only through its lifecycle; enforced by a trigger in the migration).
processing_attempt_table = Table(
    "processing_attempt",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("observation_id", BigInteger, ForeignKey("v2.observation.id", ondelete="RESTRICT"), nullable=False),
    Column("processor_id", Text, nullable=False),
    Column("processor_version", Text, nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("status", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("reason_code", Text, nullable=True),
    Column("detail_code", Text, nullable=True),
    UniqueConstraint("observation_id", "processor_id", "attempt_number", name="uq_processing_attempt_number"),
    # At most one active attempt per observation + processor.
    Index("uq_processing_attempt_one_active", "observation_id", "processor_id",
          unique=True, postgresql_where=text("status = 'processing'")),
)

# Revision 0006: UNTRUSTED candidate proposals (append-only; evidence and attempt-state enforced by triggers).
company_candidate_table = Table(
    "company_candidate",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("processing_attempt_id", BigInteger, ForeignKey("v2.processing_attempt.id", ondelete="RESTRICT"), nullable=False),
    Column("candidate_ordinal", Integer, nullable=False),
    Column("proposed_name", Text, nullable=False),
    Column("name_evidence_start", Integer, nullable=False),
    Column("name_evidence_end", Integer, nullable=False),
    Column("name_evidence_hash", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("processing_attempt_id", "candidate_ordinal", name="uq_company_candidate_ordinal"),
    comment=("UNTRUSTED PROPOSALS that evidence may describe a company. Not canonical truth: "
             "nothing here is a Company, claim or accepted identity."),
)

company_candidate_identifier_table = Table(
    "company_candidate_identifier",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("candidate_id", BigInteger, ForeignKey("v2.company_candidate.id", ondelete="RESTRICT"), nullable=False),
    Column("identifier_ordinal", Integer, nullable=False),
    Column("identifier_type", Text, nullable=False),
    Column("identifier_value", Text, nullable=False),
    Column("evidence_start", Integer, nullable=False),
    Column("evidence_end", Integer, nullable=False),
    Column("evidence_hash", Text, nullable=False),
    UniqueConstraint("candidate_id", "identifier_ordinal", name="uq_company_candidate_identifier_ordinal"),
    UniqueConstraint("candidate_id", "identifier_type", "identifier_value", name="uq_company_candidate_identifier_value"),
    comment="UNTRUSTED proposed identifiers of a company candidate. Not canonical identifiers.",
)


# Revision 0007: the resolution boundary and canonical company identity (append-only; guarded by triggers
# in the migration). Company rows may only be written by app.v2.resolution._writes.
company_table = Table(
    "company",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    comment=("TRUSTED canonical company identity anchor: an opaque id and a creation time. "
             "Created only through a create_company ResolutionDecision."),
)

resolution_decision_table = Table(
    "resolution_decision",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("candidate_id", BigInteger, ForeignKey("v2.company_candidate.id", ondelete="RESTRICT"), nullable=False),
    Column("decision_kind", Text, nullable=False),
    Column("company_id", Uuid, ForeignKey("v2.company.id", ondelete="RESTRICT"), nullable=True),
    Column("decided_by_kind", Text, nullable=False),
    Column("decided_by_id", Text, nullable=False),
    Column("reason_code", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    Index("uq_resolution_decision_one_final", "candidate_id", unique=True,
          postgresql_where=text("decision_kind IN ('create_company', 'attach_to_company', 'reject_candidate')")),
    Index("uq_resolution_decision_one_create_per_company", "company_id", unique=True,
          postgresql_where=text("decision_kind = 'create_company'")),
    comment="Append-only decisions by a RULE or a HUMAN (never AI) that resolve an untrusted company candidate.",
)

company_name_table = Table(
    "company_name",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("company_id", Uuid, ForeignKey("v2.company.id", ondelete="RESTRICT"), nullable=False),
    Column("name", Text, nullable=False),
    Column("name_role", Text, nullable=False),
    Column("resolution_decision_id", BigInteger, ForeignKey("v2.resolution_decision.id", ondelete="RESTRICT"), nullable=False),
    Column("candidate_id", BigInteger, ForeignKey("v2.company_candidate.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("company_id", "name", name="uq_company_name_company_name"),
    Index("uq_company_name_one_canonical", "company_id", unique=True, postgresql_where=text("name_role = 'canonical'")),
    comment="Canonical/alias company names accepted by a human resolution decision, with candidate provenance.",
)

company_identifier_table = Table(
    "company_identifier",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("company_id", Uuid, ForeignKey("v2.company.id", ondelete="RESTRICT"), nullable=False),
    Column("identifier_type", Text, nullable=False),
    Column("identifier_value", Text, nullable=False),
    Column("resolution_decision_id", BigInteger, ForeignKey("v2.resolution_decision.id", ondelete="RESTRICT"), nullable=False),
    Column("candidate_identifier_id", BigInteger,
           ForeignKey("v2.company_candidate_identifier.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("identifier_type", "identifier_value", name="uq_company_identifier_value"),
    UniqueConstraint("candidate_identifier_id", name="uq_company_identifier_candidate_identifier"),
    comment="Canonical normalized company identifiers accepted by a human resolution decision, with candidate provenance.",
)

# Revision 0008: UNTRUSTED financing-event candidate proposals (append-only; evidence and attempt-state enforced by
# triggers in the migration). No canonical financing_event table exists.
financing_event_candidate_table = Table(
    "financing_event_candidate",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("processing_attempt_id", BigInteger, ForeignKey("v2.processing_attempt.id", ondelete="RESTRICT", name="fk_fec_processing_attempt_id"), nullable=False),
    Column("company_id", Uuid, ForeignKey("v2.company.id", ondelete="RESTRICT", name="fk_fec_company_id"), nullable=False),
    Column("candidate_ordinal", Integer, nullable=False),
    Column("event_evidence_start", Integer, nullable=False),
    Column("event_evidence_end", Integer, nullable=False),
    Column("event_evidence_hash", Text, nullable=False),
    Column("stage", Text, nullable=False, server_default=text("'unknown'")),
    Column("stage_evidence_start", Integer, nullable=True),
    Column("stage_evidence_end", Integer, nullable=True),
    Column("stage_evidence_hash", Text, nullable=True),
    Column("financing_type", Text, nullable=False, server_default=text("'unknown'")),
    Column("type_evidence_start", Integer, nullable=True),
    Column("type_evidence_end", Integer, nullable=True),
    Column("type_evidence_hash", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("processing_attempt_id", "candidate_ordinal", name="uq_financing_event_candidate_ordinal"),
    comment=("UNTRUSTED PROPOSALS about what evidence appears to say concerning a startup financing. "
             "Not a verified or canonical financing."),
)

financing_event_candidate_amount_table = Table(
    "financing_event_candidate_amount",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("candidate_id", BigInteger, ForeignKey("v2.financing_event_candidate.id", ondelete="RESTRICT", name="fk_fec_amount_candidate_id"), nullable=False),
    Column("amount_semantics", Text, nullable=False),
    Column("currency_code", Text, nullable=False),
    Column("amount_minor_units", BigInteger, nullable=False),
    Column("evidence_start", Integer, nullable=False),
    Column("evidence_end", Integer, nullable=False),
    Column("evidence_hash", Text, nullable=False),
    UniqueConstraint("candidate_id", "amount_semantics", name="uq_financing_event_candidate_amount_semantics"),
    comment=("UNTRUSTED proposed amount of a financing candidate; the semantics column says what the amount claims "
             "to be. Not a verified round size."),
)

financing_event_candidate_date_table = Table(
    "financing_event_candidate_date",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("candidate_id", BigInteger, ForeignKey("v2.financing_event_candidate.id", ondelete="RESTRICT", name="fk_fec_date_candidate_id"), nullable=False),
    Column("date_kind", Text, nullable=False),
    Column("date_precision", Text, nullable=False),
    Column("date_start", DateTime(timezone=True), nullable=False),
    Column("evidence_start", Integer, nullable=False),
    Column("evidence_end", Integer, nullable=False),
    Column("evidence_hash", Text, nullable=False),
    UniqueConstraint("candidate_id", "date_kind", name="uq_financing_event_candidate_date_kind"),
    comment="UNTRUSTED proposed dated fact of a financing candidate, with the precision the source gave.",
)

# Revision 0009: canonical financing events and their explicit resolution (append-only; guarded by triggers in the
# migration). Canonical financing tables may only be written by app.v2.financing_resolution._writes.
financing_event_table = Table(
    "financing_event",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("company_id", Uuid, ForeignKey("v2.company.id", ondelete="RESTRICT", name="fk_fe_company_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    comment=("TRUSTED canonical financing-event identity anchor for ONE company. "
             "Created only through a create_event FinancingResolutionDecision."),
)

financing_resolution_decision_table = Table(
    "financing_resolution_decision",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("candidate_id", BigInteger, ForeignKey("v2.financing_event_candidate.id", ondelete="RESTRICT", name="fk_frd_candidate_id"), nullable=False),
    Column("decision_kind", Text, nullable=False),
    Column("financing_event_id", Uuid, ForeignKey("v2.financing_event.id", ondelete="RESTRICT", name="fk_frd_financing_event_id"), nullable=True),
    Column("decided_by_kind", Text, nullable=False),
    Column("decided_by_id", Text, nullable=False),
    Column("reason_code", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    Index("uq_frd_one_final", "candidate_id", unique=True,
          postgresql_where=text("decision_kind IN ('create_event', 'attach_to_event', 'reject_candidate')")),
    Index("uq_frd_one_create_per_event", "financing_event_id", unique=True, postgresql_where=text("decision_kind = 'create_event'")),
    comment=("Append-only decisions by a HUMAN (a rule vocabulary exists, none is enabled; never AI) "
             "that resolve an untrusted financing-event candidate."),
)


financing_event_stage_table = Table(
    "financing_event_stage",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("financing_event_id", Uuid, ForeignKey("v2.financing_event.id", ondelete="RESTRICT", name="fk_fes_financing_event_id"), nullable=False),
    Column("stage", Text, nullable=False),
    Column("resolution_decision_id", BigInteger, ForeignKey("v2.financing_resolution_decision.id", ondelete="RESTRICT", name="fk_fes_resolution_decision_id"), nullable=False),
    Column("candidate_id", BigInteger, ForeignKey("v2.financing_event_candidate.id", ondelete="RESTRICT", name="fk_fes_candidate_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("financing_event_id", name="uq_fes_one_per_event"),
    comment="Canonical stage explicitly accepted by a human decision from one candidate. Never inferred; never overwritten.",
)

financing_event_type_table = Table(
    "financing_event_type",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("financing_event_id", Uuid, ForeignKey("v2.financing_event.id", ondelete="RESTRICT", name="fk_fet_financing_event_id"), nullable=False),
    Column("financing_type", Text, nullable=False),
    Column("resolution_decision_id", BigInteger, ForeignKey("v2.financing_resolution_decision.id", ondelete="RESTRICT", name="fk_fet_resolution_decision_id"), nullable=False),
    Column("candidate_id", BigInteger, ForeignKey("v2.financing_event_candidate.id", ondelete="RESTRICT", name="fk_fet_candidate_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("financing_event_id", name="uq_fet_one_per_event"),
    comment="Canonical financing type explicitly accepted by a human decision from one candidate. Never inferred; never overwritten.",
)

financing_event_verified_round_amount_table = Table(
    "financing_event_verified_round_amount",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("financing_event_id", Uuid, ForeignKey("v2.financing_event.id", ondelete="RESTRICT", name="fk_fev_financing_event_id"), nullable=False),
    Column("currency_code", Text, nullable=False),
    Column("amount_minor_units", BigInteger, nullable=False),
    Column("resolution_decision_id", BigInteger, ForeignKey("v2.financing_resolution_decision.id", ondelete="RESTRICT", name="fk_fev_resolution_decision_id"), nullable=False),
    Column("candidate_amount_id", BigInteger,
           ForeignKey("v2.financing_event_candidate_amount.id", ondelete="RESTRICT", name="fk_fev_candidate_amount_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("financing_event_id", name="uq_fev_one_per_event"),
    UniqueConstraint("candidate_amount_id", name="uq_fev_candidate_amount"),
    comment=("Round amount VentureGPS explicitly accepted as canonical, only from a candidate announced_round_amount, "
             "only by a human decision."),
)

financing_event_date_table = Table(
    "financing_event_date",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("financing_event_id", Uuid, ForeignKey("v2.financing_event.id", ondelete="RESTRICT", name="fk_fed_financing_event_id"), nullable=False),
    Column("date_kind", Text, nullable=False),
    Column("date_precision", Text, nullable=False),
    Column("date_start", DateTime(timezone=True), nullable=False),
    Column("resolution_decision_id", BigInteger, ForeignKey("v2.financing_resolution_decision.id", ondelete="RESTRICT", name="fk_fed_resolution_decision_id"), nullable=False),
    Column("candidate_date_id", BigInteger,
           ForeignKey("v2.financing_event_candidate_date.id", ondelete="RESTRICT", name="fk_fed_candidate_date_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("financing_event_id", "date_kind", name="uq_fed_kind_per_event"),
    UniqueConstraint("candidate_date_id", name="uq_fed_candidate_date"),
    comment="Canonical semantic date explicitly accepted by a human decision from one candidate date, with its precision.",
)

# Revision 0010: minimal Market/taxonomy identity and the explicit Company -> Market classification (append-only).
taxonomy_version_table = Table(
    "taxonomy_version",
    metadata,
    Column("taxonomy_version", Text, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    comment="Registered VentureGPS taxonomy versions. Classification always names one; a methodology change is a new version, never a silent rewrite.",
)

market_table = Table(
    "market",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("slug", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("slug", name="uq_market_slug"),
    comment="A bare canonical taxonomy-node identity (not a profile): an opaque id, a routing slug, and a display name.",
)

company_market_classification_table = Table(
    "company_market_classification",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("company_id", Uuid, ForeignKey("v2.company.id", ondelete="RESTRICT", name="fk_cmc_company_id"), nullable=False),
    Column("market_id", Uuid, ForeignKey("v2.market.id", ondelete="RESTRICT", name="fk_cmc_market_id"), nullable=False),
    Column("taxonomy_version", Text,
           ForeignKey("v2.taxonomy_version.taxonomy_version", ondelete="RESTRICT", name="fk_cmc_taxonomy_version"), nullable=False),
    Column("role", Text, nullable=False),
    Column("decided_by_kind", Text, nullable=False),
    Column("decided_by_id", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    UniqueConstraint("company_id", "market_id", "taxonomy_version", name="uq_cmc_company_market_version"),
    Index("uq_cmc_one_primary_per_company_version", "company_id", "taxonomy_version", unique=True,
          postgresql_where=text("role = 'primary'")),
    comment=("Append-only, authoritative Company -> Market classification by a HUMAN (never AI), scoped to a "
             "taxonomy version. PRIMARY owns Capital attribution; SECONDARY never does."),
)
