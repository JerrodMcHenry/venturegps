"""
The second, and only other, sanctioned caller of app.v2.resolution.promotion (Increment 18.2.1).

Until Increment 18.2, app.v2.resolution.rules was the ONLY production code that ever called promotion.py --
because no local, human-facing operational tool existed at all (see the Increment 18.1 repository audit). That
was correctly enforced as a closed set by
app/v2/tests/architecture/test_resolution_boundaries.py::test_only_promotion_imports_the_private_writer_and_only_rules_import_promotion.
Increment 18.2 needed a real caller for the HUMAN side of promotion (create_company_from_candidate,
attach_candidate_to_company, reject_candidate, defer_candidate) and found none existed.

The smallest defensible fix is not to grant that access to app.v2.tools.cli, or to any other general
application module, directly: a CLI (or, later, some other operational surface) can grow new commands and new
imports over time, and "any module under app.v2.tools may reach promotion" is a materially broader grant than
"exactly one small, reviewed module may". Instead, this module is the human-authority counterpart to
resolution.rules (the deterministic-rule-authority counterpart) -- both live inside app.v2.resolution itself,
both are reviewed as part of that package, and the boundary test now asserts EXACTLY these two module names, not
a pattern or a package prefix. A caller like app.v2.tools.cli imports FROM HERE, never from
app.v2.resolution.promotion directly.

This module adds NO logic of its own: it re-exports promotion's four operations unchanged (same signatures, same
Authority re-validation inside promotion.py itself, same atomicity). It exists to be the explicit, named,
narrowly-scoped front door -- not to wrap, weaken or duplicate anything promotion.py already enforces.
"""

from app.v2.resolution.promotion import (
    PromotionResult,
    attach_candidate_to_company,
    create_company_from_candidate,
    defer_candidate,
    reject_candidate,
)

__all__ = ["PromotionResult", "attach_candidate_to_company", "create_company_from_candidate", "defer_candidate", "reject_candidate"]
