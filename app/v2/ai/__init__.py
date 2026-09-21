"""
The only place in app/v2 where AI/model-provider code may live.

AI may PROPOSE typed candidates. It may never promote them into canonical
truth, and it never holds a database handle. Rules enforced by
app/v2/tests/architecture/:

- deterministic V2 packages may not import this package (the future
  composition root app/v2/wiring.py is the single named exception);
- this package may not import V2 repositories/db writers, SQL drivers, or
  any legacy app.* module.

Ships no code yet (Phase 1, Increment 1).
"""
