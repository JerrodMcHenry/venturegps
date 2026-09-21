import pytest

from app.v2.domain.content import (
    MediaAgreement,
    MediaType,
    assess_media_agreement,
    normalize_declared_media_type,
)
from app.v2.domain.errors import InvalidInputError
from app.v2.observations import media
from app.v2.observations.media import sniff_media_type

T, H, J, P, U = (MediaType.TEXT_PLAIN, MediaType.TEXT_HTML, MediaType.APPLICATION_JSON,
                 MediaType.APPLICATION_PDF, MediaType.UNKNOWN)


@pytest.mark.parametrize(
    "data, expected",
    [
        # PDF: magic bytes at offset 0 only
        (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj", P),
        (b"%PDF-2.0", P),
        # HTML: recognised by opening bytes only, never parsed
        (b"<!DOCTYPE html><html><body>x</body></html>", H),
        (b"<!doctype HTML>\n<title>x</title>", H),
        (b"  \r\n\t<html lang='en'>", H),
        (b"\xef\xbb\xbf<html>", H),
        (b"<HTML>", H),
        (b"<html><script>alert(1)</script></html>", H),
        # JSON: only objects/arrays that strictly parse
        (b'{"a": 1}', J),
        (b"[1, 2, 3]", J),
        (b'  \n{"a": [true, null, {"b": "\xc3\xa9"}]}\n', J),
        (b'\xef\xbb\xbf{"a":1}', J),
        (b'{"a": 1, "a": 2}', J),
        # plain text
        (b"hello world", T),
        ("café ☕ 日本語".encode("utf-8"), T),
        (b"line1\r\nline2\tcol\n", T),
        (b"<div>a fragment is not treated as html</div>", T),
        (b"<htmlfoo>", T),
        (b"<!doctype html", T),
        (b'{"a": 1', T),            # looks like JSON but is not
        (b'{"a": 1}{"b": 2}', T),   # two documents
        (b'{"a": NaN}', T),         # non-standard constant
        (b"{'a': 1}", T),
        (b"123", T), (b'"str"', T), (b"true", T), (b"null", T),   # bare scalars are text
        (b"%PDF-", T), (b"%PDF-x", T), (b" %PDF-1.4", T),         # not a PDF header
        (b"x" * 1000 + b"%PDF-1.4", T),
        # unknown: empty, whitespace-only, binary, wrong encodings, control characters
        (b"", U), (b"   \n\t ", U), (b"\x00\x01\x02\x03", U), (b"\x89PNG\r\n\x1a\n\x00\x00", U),
        (b"\xff\xfe\xfa", U), (b"caf\xe9", U), (b"\xff\xfeh\x00i\x00", U),
        (b"PK\x03\x04\x14\x00", U), (b"abc\x00def", U), (b"abc\x1b[31mred", U), (b"abc\x7fdef", U),
        (b"GIF89a\x01\x00\x01\x00", U),
    ],
)
def test_sniffing_is_conservative(data, expected):
    assert sniff_media_type(data) is expected


def test_deeply_nested_json_does_not_crash_and_is_not_claimed():
    assert sniff_media_type(b"[" * 200_000 + b"]" * 200_000) is T


def test_unknown_is_never_guessed_as_something_else():
    for data in (b"", b"\x00", b"\xff", b"\x89PNG"):
        assert sniff_media_type(data) is U


def test_sniffing_is_deterministic_and_accepts_bytes_like_inputs():
    data = b'{"a": 1}'
    assert {sniff_media_type(data) for _ in range(5)} == {J}
    assert sniff_media_type(bytearray(data)) is J and sniff_media_type(memoryview(data)) is J


@pytest.mark.parametrize("value", ["text", None, 5, ["a"]])
def test_sniffing_refuses_non_bytes(value):
    with pytest.raises(InvalidInputError) as info:
        sniff_media_type(value)
    assert info.value.code == "content_must_be_bytes"


def test_oversized_content_is_refused_not_scanned(monkeypatch):
    monkeypatch.setattr(media, "MAX_SNIFF_BYTES", 10)
    assert sniff_media_type(b"x" * 10) is T
    with pytest.raises(InvalidInputError) as info:
        sniff_media_type(b"x" * 11)
    assert info.value.code == "content_too_large_to_classify"


def test_detection_takes_no_declared_type_so_it_cannot_be_overridden():
    import inspect
    assert list(inspect.signature(sniff_media_type).parameters) == ["data"]


# ---------------- declared media type

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("text/html", "text/html"),
        ("text/html; charset=UTF-8", "text/html"),
        ("  Application/JSON  ", "application/json"),
        ("APPLICATION/PDF;q=1", "application/pdf"),
        ("application/vnd.api+json", "application/vnd.api+json"),
        ("image/svg+xml", "image/svg+xml"),
        (None, None),
        ("", None), ("   ", None), (";charset=utf-8", None),
    ],
)
def test_declared_media_type_is_normalized_and_absence_stays_absent(raw, expected):
    assert normalize_declared_media_type(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["texthtml", "text/", "/html", "text//html", "text/ht ml", "text/html, text/plain", "text/html\nX-Injected: 1",
     "text/html\x00", "text/html​", "text/hтml", "K/x", "a/" + "b" * 300, "text/ht(ml)",
     5, ["text/html"], b"text/html"],
)
def test_malformed_declared_media_types_are_rejected(raw):
    with pytest.raises(InvalidInputError) as info:
        normalize_declared_media_type(raw)
    assert info.value.code == "invalid_media_type"


def test_unknown_is_not_a_valid_declared_type():
    with pytest.raises(InvalidInputError):
        normalize_declared_media_type("unknown")  # no slash: cannot collide with MediaType.UNKNOWN


# ---------------- declared vs detected

KNOWN = [T, H, J, P]


@pytest.mark.parametrize("declared", [m.value for m in KNOWN])
@pytest.mark.parametrize("detected", KNOWN)
def test_known_vs_known_is_consistent_or_conflict(declared, detected):
    expected = MediaAgreement.CONSISTENT if declared == detected.value else MediaAgreement.CONFLICT
    assert assess_media_agreement(declared, detected) is expected


@pytest.mark.parametrize("detected", [T, H, J, P, U])
def test_nothing_declared_is_unverified_never_consistent(detected):
    assert assess_media_agreement(None, detected) is MediaAgreement.UNVERIFIED


@pytest.mark.parametrize("declared", [m.value for m in KNOWN] + ["image/png", "text/csv"])
def test_unclassified_bytes_are_unverified_not_a_conflict(declared):
    assert assess_media_agreement(declared, U) is MediaAgreement.UNVERIFIED


@pytest.mark.parametrize("declared", ["image/png", "text/csv", "application/xml", "unknown"])
@pytest.mark.parametrize("detected", KNOWN)
def test_declared_types_outside_our_vocabulary_are_unverified(declared, detected):
    assert assess_media_agreement(declared, detected) is MediaAgreement.UNVERIFIED


def test_declared_type_cannot_override_detected_evidence():
    detected = sniff_media_type(b"<html><body>hi</body></html>")
    assert detected is H
    assert assess_media_agreement("application/pdf", detected) is MediaAgreement.CONFLICT
    assert detected is H  # the declared claim did not change what the bytes are
    pdf_claiming_text = sniff_media_type(b"%PDF-1.4 ...")
    assert pdf_claiming_text is P and assess_media_agreement("text/plain", pdf_claiming_text) is MediaAgreement.CONFLICT
