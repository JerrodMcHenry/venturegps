"""
The V2 AI/determinism boundary, expressed as data.

Nothing here scans anything -- boundary_scanner.py applies these rules.
Keeping the rules as one frozen dataclass means a new V2 package or a new
forbidden dependency is a one-line edit here, not a scanner change.

ZONES (derived from the module path, see boundary_scanner.zone_for_module):

  ai             app.v2.ai and everything under it. The only place model
                 providers may be imported and provider keys referenced.
  wiring         modules in `wiring_modules`. The composition root: the ONE
                 non-ai module allowed to import app.v2.ai. Does not exist
                 yet; named here so the exception is explicit, not implied.
  deterministic  EVERYTHING ELSE under app.v2 (default-deny). A package
                 added tomorrow is deterministic automatically; nobody has
                 to remember to register it.
  (excluded)     app.v2.tests -- tests legitimately import forbidden names
                 as sample data.

NO-NETWORK PACKAGES: `no_network_packages` (ingestion, repositories) may not
import any network client, socket, DNS or mail module. Ingestion receives bytes
from a trusted collector boundary; fetching is a later, separate increment.

PURE PACKAGES (a stricter layer inside the deterministic zone): every module
under `pure_packages` (app.v2.domain, app.v2.observations) is pure
computation: no database or SQL, no persistence/worker/config/migration
packages, no network, no subprocess, no environment access, and no imports
from other V2 packages beyond the pure ones. `layer_rules` adds one-way
layering (the domain never imports the packages built on it).

LIMITS: this is a static tripwire. It cannot see string-built module names
or obfuscated env names; runtime_probe.py complements it by importing the
modules in a clean subprocess and inspecting sys.modules.
"""

from dataclasses import dataclass


def matches_prefix(name: str, prefixes) -> bool:
    """Dotted-path prefix match: 'a.b' matches 'a.b' and 'a.b.c', never 'a.bc'."""
    return any(name == p or name.startswith(p + ".") for p in prefixes)


@dataclass(frozen=True)
class BoundaryRules:
    v2_root: str = "app.v2"
    ai_package: str = "app.v2.ai"
    excluded_packages: tuple[str, ...] = ("app.v2.tests",)
    wiring_modules: tuple[str, ...] = ("app.v2.wiring",)
    # The ONLY modules that may write the canonical tables (see canonical_write_tables). Everything else,
    # including every other repository, is scanned by test_resolution_boundaries.py.
    canonical_writer_modules: tuple[str, ...] = (
        "app.v2.resolution._writes", "app.v2.financing_resolution._writes", "app.v2.classification._writes",
    )
    canonical_table_variables: tuple[str, ...] = (
        "company_table", "resolution_decision_table", "company_name_table", "company_identifier_table",
        "financing_event_table", "financing_resolution_decision_table", "financing_event_stage_table",
        "financing_event_type_table", "financing_event_verified_round_amount_table", "financing_event_date_table",
        "company_market_classification_table",
    )
    canonical_table_names: tuple[str, ...] = (
        "company", "resolution_decision", "company_name", "company_identifier",
        "financing_event", "financing_resolution_decision", "financing_event_stage", "financing_event_type",
        "financing_event_verified_round_amount", "financing_event_date",
        "company_market_classification",
    )
    # Modules that may import the private writer.
    canonical_writer_importers: tuple[str, ...] = (
        "app.v2.resolution.promotion", "app.v2.financing_resolution.promotion", "app.v2.classification.service",
    )

    # Modules the static scan covers but the runtime probe cannot import
    # standalone (they only execute under Alembic).
    runtime_probe_skip_modules: tuple[str, ...] = ("app.v2.migrations.env",)

    # ---- pure packages (see docstring)
    pure_packages: tuple[str, ...] = (
        "app.v2.domain", "app.v2.observations", "app.v2.candidates.proposer", "app.v2.candidates.evidence",
        "app.v2.candidates.financing_evidence",
    )
    pure_allowed_v2_imports: tuple[str, ...] = (
        "app.v2.domain", "app.v2.observations", "app.v2.candidates.proposer", "app.v2.candidates.evidence",
        "app.v2.candidates.financing_evidence",
    )
    pure_forbidden_import_prefixes: tuple[str, ...] = (
        # database / SQL
        "sqlalchemy", "alembic", "psycopg2", "psycopg", "asyncpg", "sqlite3",
        # V2 persistence, workers, configuration (reads the environment), migrations
        "app.v2.db", "app.v2.repositories", "app.v2.workers", "app.v2.config", "app.v2.migrations",
        # environment, processes, network
        "os", "subprocess", "socket", "ssl", "http", "urllib.request", "urllib3",
        "requests", "httpx", "aiohttp", "websockets", "ftplib", "smtplib", "dotenv",
    )
    # Identifiers pure code may not even mention (environment access).
    pure_forbidden_names: tuple[str, ...] = ("environ", "environb", "getenv", "getenvb", "putenv")
    # Modules that ubiquitous stdlib/third-party code loads anyway, so the
    # RUNTIME probe checks only this subset of pure_forbidden_import_prefixes.
    pure_forbidden_loaded_prefixes: tuple[str, ...] = (
        "sqlalchemy", "alembic", "psycopg2", "psycopg", "asyncpg",
        "app.v2.db", "app.v2.repositories", "app.v2.workers", "app.v2.config", "app.v2.migrations",
        "requests", "httpx", "aiohttp", "urllib3", "websockets", "dotenv",
    )
    # (package, prefixes it may not import): one-way layering inside the pure layer.
    layer_rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("app.v2.domain", ("app.v2.observations", "app.v2.candidates")),
        ("app.v2.observations", ("app.v2.candidates",)),
    )

    # ---- candidate layer: it can never promote anything
    # The candidate layer may not import any (future) resolution/promotion/canonical package. Those packages
    # do not exist yet and must not be created just for the rule; the rule is structural.
    candidate_layer_packages: tuple[str, ...] = (
        "app.v2.candidates", "app.v2.repositories.company_candidates", "app.v2.repositories.financing_event_candidates",
    )
    canonical_forbidden_import_prefixes: tuple[str, ...] = (
        "app.v2.resolution", "app.v2.promotion", "app.v2.canonical", "app.v2.companies", "app.v2.claims",
        "app.v2.evidence_links", "app.v2.resolution_decisions", "app.v2.repositories.companies",
        "app.v2.financing_resolution", "app.v2.repositories.financing_events",
        "app.v2.classification", "app.v2.repositories.markets", "app.v2.repositories.capital_metrics",
        "app.v2.repositories.capital_signal",
    )

    # Worker, queue and scheduler frameworks: no deterministic V2 module may depend on one until
    # a worker architecture is chosen and authorised. (Matched as top-level packages.)
    worker_framework_prefixes: tuple[str, ...] = (
        "celery", "rq", "arq", "dramatiq", "huey", "kombu", "redis", "apscheduler", "schedule", "sched",
        "taskiq", "faust", "prefect", "airflow", "dask", "ray",
    )

    # ---- no-network packages (see docstring)
    no_network_packages: tuple[str, ...] = (
        "app.v2.ingestion", "app.v2.repositories", "app.v2.candidates", "app.v2.resolution", "app.v2.financing_resolution",
        "app.v2.classification",
    )
    network_forbidden_import_prefixes: tuple[str, ...] = (
        "socket", "ssl", "http", "urllib.request", "urllib3", "requests", "httpx", "aiohttp",
        "websockets", "ftplib", "smtplib", "telnetlib", "dns",
    )
    # The subset the RUNTIME probe checks (ubiquitous stdlib modules are loaded anyway).
    network_forbidden_loaded_prefixes: tuple[str, ...] = ("requests", "httpx", "aiohttp", "urllib3", "websockets")

    # Model-provider SDKs (plus Tavily: a nondeterministic external search
    # service the deterministic core must not depend on either).
    provider_sdk_prefixes: tuple[str, ...] = (
        "openai",
        "anthropic",
        "tavily",
        "google.generativeai",
        "google.genai",
        "google.ai",
        "vertexai",
        "cohere",
        "mistralai",
        "ollama",
        "groq",
        "replicate",
        "litellm",
        "transformers",
        "huggingface_hub",
        "llama_index",
        "llama_cpp",
        "tiktoken",
    )
    # Matched against the top-level component: langchain, langchain_core,
    # langchain_openai, langchain_community, ...
    provider_sdk_toplevel_starts: tuple[str, ...] = ("langchain",)

    # Provider/search configuration the deterministic core must not read or
    # even name. Matched case-insensitively as a substring of string
    # constants and identifiers.
    forbidden_env_names: tuple[str, ...] = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TAVILY_API_KEY",
    )

    # Legacy (app.*, excluding app.v2) modules deterministic V2 code may
    # import. Empty by design; add an entry only with an explicit decision
    # (for example app.observability).
    legacy_import_allowlist: tuple[str, ...] = ()

    # What app.v2.ai may import from inside V2 (default-deny for the rest).
    # Ancestor packages of an entry are implicitly allowed. app.v2.resolution is NOT listed:
    # the whole resolution/promotion boundary is closed to AI (AI may propose, never decide).
    ai_allowed_v2_imports: tuple[str, ...] = (
        "app.v2.ai",
        "app.v2.domain",
        "app.v2.candidates.proposer",
    )
    # Named persistence/write surfaces app.v2.ai must never reach. Redundant
    # with default-deny on purpose: it yields a specific rule name, and it
    # still protects if someone later widens ai_allowed_v2_imports.
    ai_forbidden_import_prefixes: tuple[str, ...] = (
        "sqlalchemy",
        "psycopg2",
        "psycopg",
        "asyncpg",
        "alembic",
        "app.v2.repositories",
        "app.v2.db",
        "app.v2.workers",
    )


DEFAULT_RULES = BoundaryRules()
