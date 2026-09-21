"""
Pure V2 domain vocabulary: value types, validation rules and state semantics.

No I/O of any kind: no database, network, environment, filesystem or AI. The
architecture tests (app/v2/tests/architecture/) enforce that for this
package and for app.v2.observations. Layering: app.v2.domain imports nothing
above itself; app.v2.observations builds on it.
"""
