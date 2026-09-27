import json
import copy
from pathlib import Path

import pytest

from build.parsers import public_domain_expansion as parser

RAW = Path(__file__).resolve().parents[1] / "raw" / "public-domain-expansion"


@pytest.mark.skipif(not RAW.exists(), reason="raw public-domain expansion files absent")
def test_builds_requested_public_domain_expansion_records():
    records = parser.build_records()
    assert {
        "roman-catechism-1829",
        "rule-of-benedict-1906",
        "apostolic-tradition-easton-1934",
        "peter-lombard-sentences-1841-vols-1-2",
        "peter-lombard-sentences-1841-vols-3-4",
        "bonaventure-opera-omnia-vol-5",
        "duns-scotus-opera-omnia-vol-8",
        "julian-revelations-divine-love",
        "cloud-of-unknowing",
    } == set(records)
    assert all(record["meta"]["license"] == "public-domain" for record in records.values())
    assert all(record["data"]["sections"] for record in records.values())


@pytest.mark.skipif(not RAW.exists(), reason="raw public-domain expansion files absent")
def test_reproduction_is_pinned_and_matches_committed_outputs():
    records = parser.build_records()

    for resource_id, record in records.items():
        provenance = record["meta"]["provenance"]
        assert provenance["download_date"] == "2026-09-17"
        assert provenance["processing_date"] == "2026-09-17"
        committed = json.loads(
            (Path(__file__).resolve().parents[1] / "data/structured-text" / f"{resource_id}.json").read_text(encoding="utf-8")
        )
        assert record == committed


@pytest.mark.skipif(not RAW.exists(), reason="raw public-domain expansion files absent")
def test_chunking_and_uncorrected_ocr_limits_are_disclosed():
    records = parser.build_records()

    for record in records.values():
        assert "6,000-character" in record["meta"]["provenance"]["notes"]
    ocr_records = [
        record
        for record in records.values()
        if record["meta"]["provenance"]["processing_method"] == "ocr"
    ]
    assert ocr_records
    assert all("uncorrected machine OCR" in record["meta"]["provenance"]["notes"] for record in ocr_records)
    assert all("does not assert textual accuracy" in record["meta"]["provenance"]["notes"] for record in ocr_records)


@pytest.mark.skipif(not RAW.exists(), reason="raw public-domain expansion files absent")
def test_translated_editions_preserve_named_contributors_and_original_languages():
    records = parser.build_records()
    expected = {
        "roman-catechism-1829": ([{"name": "Jeremiah Donovan", "role": "translator"}], "la"),
        "rule-of-benedict-1906": (
            [
                {"name": "Oswald Hunter Blair", "role": "translator"},
                {"name": "Oswald Hunter Blair", "role": "editor"},
            ],
            "la",
        ),
        "apostolic-tradition-easton-1934": (
            [{"name": "Burton Scott Easton", "role": "translator"}],
            "grc",
        ),
        "julian-revelations-divine-love": ([{"name": "Grace Warrack", "role": "editor"}], "enm"),
        "cloud-of-unknowing": ([{"name": "Evelyn Underhill", "role": "editor"}], "enm"),
    }

    for resource_id, (contributors, original_language) in expected.items():
        meta = records[resource_id]["meta"]
        assert meta["language"] == "en"
        assert meta["original_language"] == original_language
        assert all(contributor in meta["contributors"] for contributor in contributors)


@pytest.mark.skipif(not RAW.exists(), reason="raw public-domain expansion files absent")
def test_flat_text_parser_reads_contributors_and_original_language_from_config(monkeypatch):
    real_read_config = parser._read_config

    def overridden(resource_id):
        config = copy.deepcopy(real_read_config(resource_id))
        if resource_id == "rule-of-benedict-1906":
            config["contributors"] = [{"name": "Config Witness", "role": "editor"}]
            config["original_language"] = "grc"
        return config

    monkeypatch.setattr(parser, "_read_config", overridden)

    meta = parser.build_records()["rule-of-benedict-1906"]["meta"]
    assert meta["contributors"] == [{"name": "Config Witness", "role": "editor"}]
    assert meta["original_language"] == "grc"


@pytest.mark.skipif(not RAW.exists(), reason="raw public-domain expansion files absent")
def test_gutenberg_jurisdiction_notice_survives_in_each_standalone_record():
    records = parser.build_records()
    notice = (
        "This eBook is for the use of anyone anywhere in the United States and most "
        "other parts of the world at no cost and with almost no restrictions whatsoever. "
        "You may copy it, give it away or re-use it under the terms of the Project "
        "Gutenberg License included with this eBook or online at www.gutenberg.org. "
        "If you are not located in the United States, you will have to check the laws "
        "of the country where you are located before using this eBook."
    )

    for resource_id in (
        "apostolic-tradition-easton-1934",
        "julian-revelations-divine-love",
    ):
        notes = records[resource_id]["meta"]["provenance"]["notes"]
        assert notice in notes
        assert "Downstream users outside the United States must check local law." in notes


@pytest.mark.skipif(not RAW.exists(), reason="raw public-domain expansion files absent")
def test_write_records_emits_registered_writer_receipt(tmp_path):
    record = parser.build_records()["rule-of-benedict-1906"]

    parser.write_records({"rule-of-benedict-1906": record}, repo_root=tmp_path)

    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == "public_domain_expansion_parser"
    assert receipt["data_paths"] == ["data/structured-text/rule-of-benedict-1906.json"]
