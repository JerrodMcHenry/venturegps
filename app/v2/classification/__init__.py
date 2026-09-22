"""
The classification boundary: the only code that may write v2.company_market_classification.

    service.py    classify_company(db, company_id, market_id, taxonomy_version, role, authority)
    errors.py     typed refusals
    _writes.py    PRIVATE: the only module that writes the classification table

Classification changes canonical Capital attribution, so AI may not silently own it. Deterministic and
network-free: app.v2.ai may not import this package, and no classification rule is registered
(CLASSIFICATION_RULE_AUTHORITY is empty), so a rule can decide nothing. This __init__ deliberately imports nothing.
"""
