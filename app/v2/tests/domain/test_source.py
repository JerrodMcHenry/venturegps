import pytest
from pydantic import ValidationError

from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.domain.source import (
    CollectionMethod,
    Source,
    SourceType,
    validate_source_key,
    validate_source_name,
    validate_source_url,
)


def make_source(**overrides):
    base = dict(source_key="sec_edgar", name="SEC EDGAR", source_type=SourceType.GOVERNMENT_REGULATORY,
                collection_method=CollectionMethod.API, is_active=True)
    base.update(overrides)
    return Source(**base)


def test_source_type_vocabulary_is_exactly_the_approved_set():
    assert {t.value for t in SourceType} == {
        "government_regulatory", "first_party_company", "investor", "job_platform",
        "research", "patent", "open_source", "media_news", "other",
    }


def test_collection_method_vocabulary_is_small_and_explicit():
    assert {m.value for m in CollectionMethod} == {"manual_upload", "http_fetch", "api", "feed", "bulk_file"}


@pytest.mark.parametrize("source_type", list(SourceType))
def test_every_approved_source_type_builds_a_source(source_type):
    assert make_source(source_type=source_type).source_type is source_type


@pytest.mark.parametrize("method", list(CollectionMethod))
def test_every_collection_method_builds_a_source(method):
    assert make_source(collection_method=method).collection_method is method


@pytest.mark.parametrize("bad", ["", "bogus", "GOVERNMENT_REGULATORY", "government", None])
def test_invalid_source_type_is_rejected(bad):
    with pytest.raises(ValueError):
        SourceType(bad)
    with pytest.raises(ValidationError):
        make_source(source_type=bad)


def test_a_source_type_given_as_a_plain_string_is_not_silently_coerced():
    with pytest.raises(ValidationError):
        make_source(source_type="government_regulatory")


def test_source_is_immutable_closed_and_requires_an_explicit_active_flag():
    source = make_source()
    with pytest.raises(ValidationError):
        source.name = "x"
    with pytest.raises(ValidationError):
        make_source(unexpected="x")
    with pytest.raises(ValidationError):
        Source(source_key="sec_edgar", name="n", source_type=SourceType.OTHER, collection_method=CollectionMethod.API)


def test_a_source_may_have_no_url_and_none_is_not_defaulted_to_anything():
    assert make_source().url is None
    assert make_source(url=None).url is None


@pytest.mark.parametrize("key", ["sec_edgar", "ab", "a1", "greenhouse_jobs", "x" * 64])
def test_valid_source_keys(key):
    assert validate_source_key(key) == key


@pytest.mark.parametrize("key", ["", "a", "Sec_Edgar", "1abc", "_abc", "sec-edgar", "sec edgar", "sec_edgar\n", "x" * 65, "sëc", None, 5])
def test_invalid_source_keys(key):
    with pytest.raises(InvalidInputError) as info:
        validate_source_key(key)
    assert info.value.code == "invalid_source_key"


@pytest.mark.parametrize("name", ["SEC EDGAR", "A", "Crunchbase (public)", "x" * 200])
def test_valid_source_names(name):
    assert validate_source_name(name) == name


@pytest.mark.parametrize("name", ["", " lead", "trail ", "a\nb", "a\x00b", "x" * 201, None, 5])
def test_invalid_source_names(name):
    with pytest.raises(InvalidInputError):
        validate_source_name(name)


# ---------------- source URLs: data only, never fetched (the conftest blocks all network access)

@pytest.mark.parametrize(
    "url",
    [
        "https://example.com", "http://example.com", "https://example.com/", "https://example.com:8443/a/b?x=1&y=2#frag",
        "https://sub.example.co.uk/path", "HTTPS://Example.COM/Path", "https://[2001:db8::1]/x", "https://127.0.0.1/", "http://localhost:3000",
    ],
)
def test_valid_source_urls_are_accepted_unchanged(url):
    assert validate_source_url(url) == url
    assert make_source(url=url).url == url


@pytest.mark.parametrize(
    "url",
    ["https://user:pw@example.com/", "https://user@example.com/", "https://:pw@example.com/",
     "https://example.com@evil.com/", "http://a:b@[::1]/", "ftp://u:p@example.com/"],
)
def test_embedded_credentials_are_rejected(url):
    with pytest.raises(InvalidInputError) as info:
        validate_source_url(url)
    assert info.value.code == "url_credentials"


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/x", "file:///etc/passwd", "javascript:alert(1)", "data:text/html,x", "gopher://x",
     "//example.com/x", "example.com", "mailto:a@b.co".replace("a@b.co", "x"), "ws://example.com", "s3://bucket/key"],
)
def test_unsupported_schemes_are_rejected(url):
    with pytest.raises(UnsupportedInputError) as info:
        validate_source_url(url)
    assert info.value.code == "unsupported_url_scheme"


@pytest.mark.parametrize(
    "url",
    ["", "https://", "https:///path", "https://exa mple.com", "https://example.com/a b", "https://example.com/\n",
     "https://example.com/\t", "https://example.com\\evil.com", "https://exämple.com", "https://еxample.com",
     "https://example.com:99999", "https://example.com:abc", "https://[::1/x", "https://" + "a" * 254 + ".com",
     "https://example.com/" + "a" * 2048, None, 5, b"https://example.com"],
)
def test_malformed_urls_are_rejected(url):
    with pytest.raises(InvalidInputError):
        validate_source_url(url)


def test_url_at_the_length_limit_is_accepted():
    url = "https://example.com/" + "a" * (2048 - len("https://example.com/"))
    assert len(url) == 2048 and validate_source_url(url) == url
