"""
PRIVATE. The ONLY module that writes v2.company_market_classification. app.v2.classification.service is the only
importer; an architecture test fails if any other module writes this table or imports this one.

Nothing here decides anything: it takes an already-validated Authority and inserts exactly the row the calling
operation has justified. The database re-verifies it (role/authority CHECKs, the one-primary partial unique index,
the every-rule-refused guard trigger).
"""

from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from app.v2.db.tables import company_market_classification_table as cmc
from app.v2.domain.resolution import Authority
from app.v2.domain.taxonomy import ClassificationRole


def insert_classification(connection: Connection, *, company_id: UUID, market_id: UUID, taxonomy_version: str,
                          role: ClassificationRole, authority: Authority) -> int:
    return connection.execute(insert(cmc).values(
        company_id=company_id, market_id=market_id, taxonomy_version=taxonomy_version, role=role.value,
        decided_by_kind=authority.kind.value, decided_by_id=authority.id,
    ).returning(cmc.c.id)).scalar_one()
