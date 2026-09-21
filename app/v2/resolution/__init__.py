"""
The resolution boundary: the only code that may turn an untrusted CompanyCandidate into canonical identity.

    promotion.py  the four explicit operations (create / attach / reject / defer)
    rules.py      the one deterministic rule (exact identifier match => attach)
    errors.py     typed refusals
    _writes.py    PRIVATE: the only module that writes the canonical tables

This package is deterministic and network-free. app.v2.ai may not import it (default-deny),
no provider SDK is reachable from it, and nothing here takes a confidence or a model output
as input. This __init__ deliberately imports nothing.
"""
