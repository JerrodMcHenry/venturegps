"""
Financing-event candidates: UNTRUSTED PROPOSALS about what evidence appears to say concerning a startup financing.

    Observation  !=  FinancingEventCandidate  !=  (future) canonical FinancingEvent

A FinancingEventCandidate answers "what exactly is VentureGPS being TOLD may have happened?" without
ever saying "this financing happened". Nothing here is a verified round, a venture round, a funding
amount or a metric; nothing here can be promoted (no canonical FinancingEvent exists in V2 yet). The
types are deliberately named Proposed/Candidate.

Capital methodology v0.1 rules these types encode:
  - Amount semantics are NEVER collapsed. Three are proposable:
        offering_amount          what an offering says may be offered      (e.g. SEC Form D "total offering amount")
        amount_sold              what a filing says HAS been sold          (e.g. Form D "total amount sold")
        announced_round_amount   what an announcement says the round was   (e.g. "Acme announced a $20M Series A")
    None of them is a verified round size; there is no verified_round_amount and no generic "amount" or
    "funding_amount". Verification belongs to a later, separately reviewed resolution layer.
  - Dates are NEVER collapsed: first_sale_date, filing_date, announcement_date. Each keeps the precision the
    source gave (EventTime): a year-only date stays a year, a month a month. There is no generic event_date, and
    Observation.observed_time (when WE saw it) is a different clock again.
  - UNKNOWN STAYS UNKNOWN. A stage or financing type exists only if the evidence states it; it is never inferred
    from an amount, company age, an investor, headcount or a model's guess. Absence is `unknown`.
  - Money is exact: integer minor units plus an explicit ISO-4217 currency. Never a float; never an assumed USD;
    no FX conversion. If the currency cannot be established from evidence the amount is not proposed at all.
  - Every substantive fact carries its own byte-exact evidence locator (see app.v2.domain.candidate.EvidenceLocator),
    and the candidate as a whole carries event-level evidence that a financing occurrence is being proposed: a bare
    "$5 million" with nothing tying it to a financing is not a candidate.
  - The company is identified ONLY by a canonical Company id (v2.company). Never a name, domain or URL: if the
    evidence describes an unknown company, company resolution must happen first (Candidate -> ResolutionDecision -> Company).

Candidate identity is (processing_attempt_id, candidate_ordinal). The ordinal is the proposal's position in the
proposer's output, which is only stable while proposers are deterministic; when a real probabilistic proposer is
introduced this identity must be reconsidered (content-derived identity) before it is relied on.
"""

from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from types import MappingProxyType
from typing import ClassVar
from uuid import UUID

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.time import EventTime, UtcDatetime

MAX_FINANCING_CANDIDATES_PER_ATTEMPT = 50
MAX_MINOR_UNITS = 2**63 - 1   # the database column is BIGINT


class Stage(str, Enum):
    """Explicit stage vocabulary. UNKNOWN is the default and is never inferred."""

    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    GROWTH = "growth"
    UNKNOWN = "unknown"


class FinancingType(str, Enum):
    """Candidate-level instrument vocabulary. UNKNOWN unless the evidence states it; OTHER = stated, but not one of these."""

    EQUITY = "equity"
    CONVERTIBLE = "convertible"
    DEBT = "debt"
    OTHER = "other"
    UNKNOWN = "unknown"


class AmountSemantics(str, Enum):
    OFFERING_AMOUNT = "offering_amount"
    AMOUNT_SOLD = "amount_sold"
    ANNOUNCED_ROUND_AMOUNT = "announced_round_amount"


class FinancingDateKind(str, Enum):
    FIRST_SALE_DATE = "first_sale_date"
    FILING_DATE = "filing_date"
    ANNOUNCEMENT_DATE = "announcement_date"


# ISO-4217 code -> number of minor-unit decimal places. An explicit, small allowlist: a currency outside it cannot
# be proposed until it is added here on purpose (there is no guessing and no FX).
CURRENCY_MINOR_UNIT_EXPONENTS = MappingProxyType({
    "USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "AUD": 2, "CHF": 2, "SEK": 2, "SGD": 2, "INR": 2, "ILS": 2, "CNY": 2, "JPY": 0,
})


class Money(DomainModel):
    """An exact amount: integer minor units (cents for USD) in an explicit currency. No float, no default currency."""

    currency_code: str
    minor_units: int = Field(ge=0, le=MAX_MINOR_UNITS)

    @model_validator(mode="after")
    def _currency_is_supported(self) -> "Money":
        if self.currency_code not in CURRENCY_MINOR_UNIT_EXPONENTS:
            raise InvalidInputError("unsupported_currency", "currency must be an explicitly supported ISO-4217 code")
        return self

    @classmethod
    def from_decimal(cls, amount: object, currency_code: str) -> "Money":
        """Exact conversion from an int, a Decimal or a decimal string. Floats and bools are refused; an amount with
        finer precision than the currency's minor unit is refused rather than rounded."""
        if isinstance(amount, (float, bool)) or not isinstance(amount, (int, str, Decimal)):
            raise InvalidInputError("invalid_amount", "amount must be an int, a Decimal or a decimal string (never a float)")
        if currency_code not in CURRENCY_MINOR_UNIT_EXPONENTS:
            raise InvalidInputError("unsupported_currency", "currency must be an explicitly supported ISO-4217 code")
        try:
            value = Decimal(amount)
        except (InvalidOperation, ValueError):
            raise InvalidInputError("invalid_amount", "amount is not a decimal number") from None
        if not value.is_finite() or value < 0:
            raise InvalidInputError("invalid_amount", "amount must be a finite non-negative number")
        with localcontext() as context:
            context.prec = 60
            try:
                scaled = value.scaleb(CURRENCY_MINOR_UNIT_EXPONENTS[currency_code])
            except ArithmeticError:
                raise InvalidInputError("amount_too_large", "amount exceeds the exact range that can be stored") from None
            if scaled > MAX_MINOR_UNITS:
                raise InvalidInputError("amount_too_large", "amount exceeds the exact range that can be stored")
            if scaled != scaled.to_integral_value():
                raise InvalidInputError("amount_finer_than_currency_unit", "amount has more decimal places than the currency's minor unit")
            minor = int(scaled)
        return cls(currency_code=currency_code, minor_units=minor)


class ProposedStage(DomainModel):
    """A stage the evidence STATES. There is no way to propose 'unknown': absence is unknown."""

    stage: Stage
    evidence: EvidenceLocator

    @model_validator(mode="after")
    def _is_a_stated_stage(self) -> "ProposedStage":
        if self.stage is Stage.UNKNOWN:
            raise InvalidInputError("unknown_stage_is_absence", "an unknown stage is expressed by proposing no stage")
        return self


class ProposedFinancingType(DomainModel):
    financing_type: FinancingType
    evidence: EvidenceLocator

    @model_validator(mode="after")
    def _is_a_stated_type(self) -> "ProposedFinancingType":
        if self.financing_type is FinancingType.UNKNOWN:
            raise InvalidInputError("unknown_type_is_absence", "an unknown financing type is expressed by proposing none")
        return self


class ProposedAmount(DomainModel):
    semantics: AmountSemantics
    money: Money
    evidence: EvidenceLocator


class ProposedFinancingDate(DomainModel):
    kind: FinancingDateKind
    time: EventTime          # keeps its precision: a year is a year, never a fabricated day
    evidence: EvidenceLocator


class FinancingEventCandidateProposal(DomainModel):
    """Unpersisted output of a proposer/extractor. Carries no confidence, model, provider or prompt fields."""

    company_id: UUID                       # a CANONICAL company; never a name, domain or URL
    event_evidence: EvidenceLocator        # evidence that a financing occurrence is being proposed
    stage: ProposedStage | None = None     # None == unknown
    financing_type: ProposedFinancingType | None = None   # None == unknown
    amounts: tuple[ProposedAmount, ...] = ()
    dates: tuple[ProposedFinancingDate, ...] = ()

    @model_validator(mode="after")
    def _each_semantic_appears_once(self) -> "FinancingEventCandidateProposal":
        if len({a.semantics for a in self.amounts}) != len(self.amounts):
            raise InvalidInputError("duplicate_amount_semantics", "each amount semantics may be proposed at most once per candidate")
        if len({d.kind for d in self.dates}) != len(self.dates):
            raise InvalidInputError("duplicate_date_kind", "each date kind may be proposed at most once per candidate")
        return self

    @property
    def stage_value(self) -> Stage:
        return self.stage.stage if self.stage else Stage.UNKNOWN

    @property
    def financing_type_value(self) -> FinancingType:
        return self.financing_type.financing_type if self.financing_type else FinancingType.UNKNOWN


class StoredFinancingEventCandidate(DomainModel):
    """A persisted, immutable, STILL UNTRUSTED proposal. Not a financing, not verified, not canonical."""

    TRUST_LEVEL: ClassVar[str] = "untrusted_proposal"

    id: int = Field(gt=0)
    processing_attempt_id: int = Field(gt=0)
    candidate_ordinal: int = Field(ge=1)
    proposal: FinancingEventCandidateProposal
    created_at: UtcDatetime     # assigned by the database
