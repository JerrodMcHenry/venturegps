import pytest
from pydantic import BaseModel

from app.v2.domain.errors import InvalidInputError
from app.v2.domain.versions import (
    VersionId,
    is_valid_version_id,
    make_version_id,
    validate_version_id,
    version_name,
    version_number,
)


@pytest.mark.parametrize(
    "value",
    ["manual_upload.v1", "byte_range_match.v2", "a.v1", "x9_y.v999999", "collector_2.v10", "a" * 64 + ".v1", "openai_proposer.v3"],
)
def test_valid_identifiers_are_accepted(value):
    assert validate_version_id(value) == value and is_valid_version_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "", "manual", "manual.v", "manual.v0", "manual.v01", "manual.v1234567", "manual.V1", "Manual.v1",
        "1manual.v1", "_manual.v1", "manual-upload.v1", "manual.v1.v2", "manual..v1", ".v1", "manual v1",
        " manual.v1", "manual.v1 ", "manual.v1\n", "\nmanual.v1", "manual.v-1", "manual.v1.0", "v1",
        "a" * 65 + ".v1", "mánual.v1", "manual.v１",  # fullwidth digit
        1, None, b"manual.v1", ["manual.v1"], 1.5,
    ],
)
def test_malformed_identifiers_are_rejected(value):
    with pytest.raises(InvalidInputError) as info:
        validate_version_id(value)
    assert info.value.code == "invalid_version_id"
    assert not is_valid_version_id(value)


def test_equality_and_construction_are_stable():
    assert make_version_id("manual_upload", 1) == "manual_upload.v1"
    assert make_version_id("manual_upload", 1) == make_version_id("manual_upload", 1)
    assert make_version_id("manual_upload", 1) != make_version_id("manual_upload", 2)
    assert make_version_id("manual_upload", 1) != make_version_id("manual_fetch", 1)


def test_name_and_number_round_trip():
    assert version_name("byte_range_match.v12") == "byte_range_match"
    assert version_number("byte_range_match.v12") == 12
    assert make_version_id(version_name("x_y.v7"), version_number("x_y.v7")) == "x_y.v7"
    assert version_number("p.v2") > version_number("p.v1")  # ordering only meaningful within one name


@pytest.mark.parametrize("name, number", [("Bad", 1), ("ok", 0), ("ok", -1), ("ok", 1.0), ("ok", True), ("ok", "1")])
def test_make_version_id_validates(name, number):
    with pytest.raises(InvalidInputError):
        make_version_id(name, number)


def test_version_id_works_as_a_model_field_annotation():
    class Holder(BaseModel):
        version: VersionId

    assert Holder(version="rule_x.v3").version == "rule_x.v3"
    with pytest.raises(InvalidInputError):
        Holder(version="rule_x")
