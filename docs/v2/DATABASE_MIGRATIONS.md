# VentureGPS V2 database migrations and test databases

Status: Phase 1, Increment 2. See ADR-0001 for the truth model.

## Architecture

| Piece | Location |
|---|---|
| Alembic config | `alembic.ini` (repo root; no database URL in it) |
| Environment | `app/v2/migrations/env.py` |
| Revisions | `app/v2/migrations/versions/` (numbered `0001_...`) |
| V2 config (lazy env reads) | `app/v2/config.py` |
| Engine factory (lazy, small pool) | `app/v2/db/engine.py` |
| Schema metadata | `app/v2/db/metadata.py` |
| Table definitions (shape only; one per increment) | `app/v2/db/tables.py` |
| Source persistence | `app/v2/repositories/sources.py` (+ `errors.py`) |
| What Alembic may see | `app/v2/db/scope.py` |
| Migration lock | `app/v2/db/locks.py` |

- **Schema `v2`, version table `v2.alembic_version`.** Never `public`.
- **Legacy is not adopted.** No baseline, no stamp, no conversion of legacy DDL.
  Legacy `add_*()` functions are frozen and untouched. V2 migrations do not depend
  on any legacy object existing.
- **Scoping is fail-closed and two-layered.** `include_name` stops Alembic from
  reflecting any schema except `v2` (including the default schema, where legacy
  tables live); `include_object` admits only objects belonging to a `v2` table.
  `alembic check` with legacy tables present reports no drift.
- **Never automatic.** Migrations do not run at import or FastAPI startup, and V2
  application code may not call `alembic.command` (enforced by a test).
- **The engine is lazy.** Importing `app.v2.config` / `app.v2.db.*` reads no
  environment, opens no connection and needs no AI configuration (tested in a clean
  subprocess with `create_engine` and `psycopg2.connect` booby-trapped).
  Pool: 2 + 2 overflow, `pool_pre_ping`, `application_name=venturegps-v2`.

### Bootstrap and teardown

Alembic creates its version table before running any revision, and that table lives
in `v2`, so the schema must already exist. `env.py` therefore runs
`CREATE SCHEMA IF NOT EXISTS v2` first, but only for commands that upgrade or stamp
to a revision. `current`, `heads`, `history` and `check` create nothing.

Revision `0001` records the namespace (idempotent `CREATE SCHEMA IF NOT EXISTS`
plus a comment on the schema) and creates no tables. Its downgrade removes the
comment. When a downgrade reverts everything to base, `env.py` then drops
`v2.alembic_version` and schema `v2` in the same transaction; `DROP SCHEMA` has no
`CASCADE`, so if anything else lives in `v2` the entire downgrade rolls back.

### Revision 0002: `v2.source`

The persisted form of the pure `Source` model (`app/v2/domain/source.py`). Identity is a
generated `id` plus the unique `source_key`; name and URL are data, never identity.

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | primary key `pk_source` |
| `source_key` | `TEXT NOT NULL` | `uq_source_source_key`; shape check `^[a-z][a-z0-9_]{1,63}$` |
| `source_name` | `TEXT NOT NULL` | no surrounding spaces, 1-200 chars, no control characters |
| `source_type` | `TEXT NOT NULL` | `CHECK IN` the nine `SourceType` values |
| `collection_method` | `TEXT NOT NULL` | `CHECK IN` the five `CollectionMethod` values |
| `source_url` | `TEXT NULL` | null allowed; if set: <= 2048, printable ASCII, `http(s)://host`, no userinfo |
| `is_active` | `BOOLEAN NOT NULL` | no default: it must be stated |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | database-assigned, immutable |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | moves only when a mutable field changes |

Also `CHECK (updated_at >= created_at)`.

- **Enums are `TEXT` + named `CHECK`s, not PostgreSQL `ENUM` types.** Extending a vocabulary is
  one constraint swap in an ordinary transactional migration; `ENUM` values cannot be removed
  and `ADD VALUE` has transaction restrictions. The Python enums stay authoritative; the
  CHECKs guard integrity and are deliberately a subset of the domain rules (for example the
  database trims only spaces where the domain rejects any surrounding whitespace, so a row the
  database accepts can still be refused by the domain on load and is reported, not returned).
- **Immutable after insert: `id`, `source_key`, `source_type`, `collection_method`,
  `created_at`. Mutable: `source_name`, `source_url`, `is_active`.** One
  `BEFORE INSERT OR UPDATE` trigger (`v2.source_guard`) enforces this for every writer,
  including direct SQL, and rejects an update that bundles a legal change with an illegal one
  as a whole. It also owns the timestamps: `created_at` is always the database clock (a
  caller-supplied value is overwritten), and `updated_at` moves only when a mutable field
  actually changes (a no-op update, or a caller-supplied `updated_at`, does not).
- **Repository semantics.** `register_source` is create-only with idempotent replay: a new key
  is created; an existing key with the same `source_type` and `collection_method` returns the
  existing Source unchanged (registration never rewrites name/url/is_active); a different
  `source_type` or `collection_method` raises `ConflictError`. There is no delete operation:
  a Source is deactivated (`is_active = false`), which keeps the row and changes nothing else.

### Concurrency

A PostgreSQL session-level advisory lock (`MIGRATION_LOCK_KEY`) is held for the whole
run. It is try-lock plus polling with a timeout (default 30s), so a stuck migrator
produces a clear `MigrationLockError` instead of an indefinite wait.

### Rollback policy

`downgrade` is supported and tested for disposable, dev and test databases. Once V2
contains real evidence, destructive production downgrades are not the recovery
strategy: back up first and prefer forward fixes (expand/contract). No backup
infrastructure exists yet.

## Running the V2 database tests

`python -m pytest` runs the whole V2 suite. Tests marked `db` need a disposable
PostgreSQL database and are **skipped** when `V2_TEST_DATABASE_URL` is unset
(**failed** when `V2_REQUIRE_DB_TESTS=1`, which CI should set).

### The exact safety rule

A database may be used by V2 DB tests only if **all** of these hold
(`app/v2/tests/db/guard.py`, tested in `test_database_guard.py`):

1. `V2_TEST_DATABASE_URL` is set. **There is no fallback** to `DATABASE_URL`,
   `V2_DATABASE_URL` or anything else. V2 tests also remove those two variables
   from the process environment, so nothing they start can inherit a production URL.
2. It is a PostgreSQL URL (`postgresql` / `postgresql+psycopg2`).
3. The database **name** matches `^venturegps_v2_test(_[a-z0-9]+)?$`
   (for example `venturegps_v2_test`, `venturegps_v2_test_w1`).
4. The host is loopback (`localhost`, `127.0.0.1`, `::1`), a unix-socket path, or
   listed exactly in `V2_TEST_DATABASE_ALLOWED_HOSTS` (comma-separated). Loopback
   alone is not enough (rules 3 and 6 still apply), and a remote host needs an
   explicit opt-in.
5. The database name differs from the name in `DATABASE_URL` / `V2_DATABASE_URL`,
   whatever host they use.
6. Before any destructive statement, the **server** attests that it is disposable:
   `current_database()` equals the URL's database and the database comment is
   exactly `VENTUREGPS_V2_DISPOSABLE_TEST_DB`.

An unset URL skips. An unsafe URL **fails loudly** (`REFUSING to run V2 database
tests: ...`); it is never skipped, corrected or retried. Error messages never
contain the URL. Test cleanup only drops schema `v2` and the `legacy_probe_*` /
`public.alembic_version` decoy objects that the tests themselves create.

### Creating a test database

```bash
createdb venturegps_v2_test
psql -d venturegps_v2_test -c "COMMENT ON DATABASE venturegps_v2_test IS 'VENTUREGPS_V2_DISPOSABLE_TEST_DB'"
export V2_TEST_DATABASE_URL='postgresql://localhost/venturegps_v2_test'
V2_REQUIRE_DB_TESTS=1 python -m pytest
```

Use a dedicated database (or a throwaway cluster on another port). Do not reuse a
database that holds anything you care about; the tests drop schema `v2` in it.

### What the DB tests prove

Upgrade base to head (and 0001 to 0002 to 0001 stepwise), downgrade head to base, upgrade again, idempotent upgrade;
the version table is `v2.alembic_version` and never `public`; a `public.alembic_version`
decoy and representative legacy tables (data, indexes, constraints, sequences, a view)
are byte-for-byte unchanged across upgrade, downgrade and re-upgrade; `alembic check`
sees no legacy drift; the filters (not luck) are what exclude legacy tables; downgrade
refuses to drop a schema holding foreign objects and rolls back completely; the advisory
lock makes a second migrator fail fast, and four concurrent `alembic upgrade head`
processes serialize with exactly one applying the revision.
