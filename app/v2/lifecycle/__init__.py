"""
The lifecycle resolution boundary: the only code that may turn an untrusted LifecycleEventCandidate into
accepted canonical lifecycle facts about an ALREADY-canonical Company (Increment 18.7).

    promotion.py  the three explicit operations (accept_lifecycle_event / reject / defer) and fact selection
    errors.py     typed refusals
    _writes.py    PRIVATE: the only module that writes the canonical lifecycle tables

Unlike app.v2.financing_resolution there is no create/attach split: a lifecycle candidate never brings a new
entity into existence, it always annotates a company that already exists. Deterministic and network-free:
app.v2.ai may not import it, and no lifecycle rule is registered (LIFECYCLE_RULE_AUTHORITY is empty), so a
rule can decide nothing -- lifecycle identity judgment calls are human-only, same stance as financing. This
__init__ deliberately imports nothing.
"""
