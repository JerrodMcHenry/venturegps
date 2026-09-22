"""
The financing resolution boundary: the only code that may turn an untrusted FinancingEventCandidate into a
canonical FinancingEvent, or attach further candidates to one.

    promotion.py  the four explicit operations (create_event / attach_to_event / reject / defer) and fact selection
    errors.py     typed refusals
    _writes.py    PRIVATE: the only module that writes the canonical financing tables

This is deliberately NOT a generalisation of app.v2.resolution (Company identity): financing-event identity has
different semantics (many candidates may describe one event; facts are selected, never blindly copied). Deterministic
and network-free: app.v2.ai may not import it, and no financing rule is registered (FINANCING_RULE_AUTHORITY is empty),
so a rule can decide nothing. This __init__ deliberately imports nothing.
"""
