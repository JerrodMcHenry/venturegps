"""
Conservative, deterministic media sniffing over raw bytes.

Only the Phase 1 formats are recognised; everything else -- including empty,
whitespace-only, non-UTF-8 and binary content -- is UNKNOWN. The detector
never renders, executes or interprets active content: HTML is recognised by
its opening bytes only (never parsed), PDFs by their magic bytes only, and
JSON (plain data) is checked by strict parsing.

Order: PDF, HTML, JSON, then plain text. Anything a stricter rule claimed is
not offered to a looser one.

The declared media type never influences detection; the two are compared
separately by app.v2.domain.content.assess_media_agreement().
"""

import json
import re

from app.v2.domain.content import MediaType
from app.v2.domain.errors import InvalidInputError

# Safety net only; the real payload cap is enforced at ingestion.
MAX_SNIFF_BYTES = 16 * 1024 * 1024

_PDF_MAGIC = re.compile(rb"%PDF-[0-9]")
_HTML_START = re.compile(r"(?i)<!doctype\s+html(?=[\s>])|<html(?=[\s>])")
# C0 controls other than \t \n \f \r, plus DEL. NUL in particular means binary.
_DISALLOWED_TEXT_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


def _reject_constant(_name: str):
    raise ValueError("non-standard JSON constant")


def _is_json_container(text: str) -> bool:
    stripped = text.lstrip(" \t\r\n")
    if not stripped or stripped[0] not in "{[":
        return False  # bare scalars are treated as plain text, not JSON
    try:
        json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return False
    return True


def sniff_media_type(data: bytes | bytearray | memoryview) -> MediaType:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise InvalidInputError("content_must_be_bytes", "content must be bytes")
    raw = bytes(data)
    if len(raw) > MAX_SNIFF_BYTES:
        raise InvalidInputError("content_too_large_to_classify", "content is too large to classify")

    if _PDF_MAGIC.match(raw):
        return MediaType.APPLICATION_PDF

    try:
        text = raw.decode("utf-8-sig")  # strict UTF-8; tolerates a leading BOM
    except UnicodeDecodeError:
        return MediaType.UNKNOWN
    if not text.strip() or _DISALLOWED_TEXT_CONTROLS.search(text):
        return MediaType.UNKNOWN

    if _HTML_START.match(text.lstrip(" \t\r\n")):
        return MediaType.TEXT_HTML
    if _is_json_container(text):
        return MediaType.APPLICATION_JSON
    return MediaType.TEXT_PLAIN
