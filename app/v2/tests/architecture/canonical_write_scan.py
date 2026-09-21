"""
Static scan for WRITES to the canonical tables (company, resolution_decision, company_name, company_identifier).

Only modules in DEFAULT_RULES.canonical_writer_modules may write them. A write is: calling
.insert()/.update()/.delete() on a canonical table object (or an alias of it), passing one to
insert()/update()/delete()/pg_insert(), or a string constant that is SQL writing to a canonical
table. Reads (select) are unrestricted. Like the rest of the scanner this is a tripwire, not a proof:
the database triggers are the backstop for anything it cannot see.
"""

import ast
import re

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES, BoundaryRules
from app.v2.tests.architecture.boundary_scanner import module_name_for

_WRITE_VERBS = {"insert", "update", "delete", "pg_insert", "merge"}


def _sql_write_pattern(rules: BoundaryRules) -> re.Pattern:
    tables = "|".join(re.escape(t) for t in rules.canonical_table_names)
    return re.compile(rf"\b(insert\s+into|update|delete\s+from|truncate(?:\s+table)?)\s+(?:only\s+)?(?:v2\.)?({tables})\b", re.I)


def canonical_writes(source: str, rel_path: str, rules: BoundaryRules = DEFAULT_RULES) -> list[str]:
    """Descriptions of canonical-table writes found in `source` (empty for an approved writer module)."""
    named = module_name_for(rel_path)
    if named is not None and named[0] in rules.canonical_writer_modules:
        return []
    tree = ast.parse(source)
    aliases = set(rules.canonical_table_variables)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for item in node.names:
                if item.name in rules.canonical_table_variables:
                    aliases.add(item.asname or item.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    found: list[str] = []
    pattern = _sql_write_pattern(rules)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _WRITE_VERBS and isinstance(func.value, ast.Name) and func.value.id in aliases:
                found.append(f"{func.value.id}.{func.attr}()")
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in _WRITE_VERBS and any(isinstance(a, ast.Name) and a.id in aliases for a in node.args):
                found.append(f"{name}(<canonical table>)")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and pattern.search(node.value):
            found.append("raw SQL write")
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str) \
                and node.slice.value.removeprefix("v2.") in rules.canonical_table_names:
            found.append("metadata.tables[<canonical table>]")                # reaching a canonical table by name: not allowed outside the writer
    return found
