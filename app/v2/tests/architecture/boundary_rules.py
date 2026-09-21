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
    # Modules the static scan covers but the runtime probe cannot import
    # standalone (they only execute under Alembic).
    runtime_probe_skip_modules: tuple[str, ...] = ("app.v2.migrations.env",)

    # ---- pure packages (see docstring)
    pure_packages: tuple[str, ...] = ("app.v2.domain", "app.v2.observations")
    pure_allowed_v2_imports: tuple[str, ...] = ("app.v2.domain", "app.v2.observations")
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
        ("app.v2.domain", ("app.v2.observations",)),
    )

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
    # Ancestor packages of an entry are implicitly allowed, so
    # `from app.v2.resolution import ports` works while
    # `from app.v2.resolution import promote` does not.
    ai_allowed_v2_imports: tuple[str, ...] = (
        "app.v2.ai",
        "app.v2.domain",
        "app.v2.resolution.ports",
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
