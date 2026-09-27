from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from build.parsers import schaff_ecumenical_creeds as parser  # noqa: E402

RAW_1 = REPO_ROOT / "raw" / "ccel" / "schaff" / "creeds1.xml"
RAW_2 = REPO_ROOT / "raw" / "ccel" / "schaff" / "creeds2.xml"


@pytest.mark.skipif(not (RAW_1.exists() and RAW_2.exists()), reason="raw Schaff XML absent")
def test_extracts_three_distinct_nicene_forms():
    records = parser.extract_records()

    assert set(records) == {
        "nicene-creed-325",
        "nicene-creed",
        "nicene-creed-anglican-bcp-1662",
    }

    creed_325 = records["nicene-creed-325"]["data"]["units"][0]["content"]
    creed_381 = records["nicene-creed"]["data"]["units"][0]["content"]
    western = records["nicene-creed-anglican-bcp-1662"]["data"]["units"][0]["content"]

    assert "of the essence of the Father" in creed_325
    assert "whose kingdom shall have no end" not in creed_325.lower()
    assert "whose kingdom shall have no end" in creed_381.lower()
    assert "proceedeth from the Father" in creed_381
    assert "proceedeth from the Father and the Son" not in creed_381
    assert "proceedeth from the Father [and the Son]" in western


@pytest.mark.skipif(not (RAW_1.exists() and RAW_2.exists()), reason="raw Schaff XML absent")
def test_anglican_bcp_witness_is_exact_and_preserves_schaff_brackets():
    record = parser.extract_records()["nicene-creed-anglican-bcp-1662"]
    meta = record["meta"]
    text = record["data"]["units"][0]["content"]

    assert meta["title"] == (
        "Niceno-Constantinopolitan Creed: Anglican Book of Common Prayer (1662), "
        "Schaff Protestant Received Text"
    )
    assert meta["author"] == "Church of England"
    assert meta["original_publication_year"] == 1662
    assert "Anglican Book of Common Prayer (1662)" in meta["provenance"]["source_edition"]
    assert "Protestant received-text column" in meta["provenance"]["notes"]
    assert "Western additions" in meta["provenance"]["notes"]
    assert "before all worlds [God of God], Light of Light" in text
    assert "one substance [essence] with the Father" in text
    assert "And [I believe] in the Holy Ghost" in text
    assert "Father [and the Son]" in text


@pytest.mark.skipif(not (RAW_1.exists() and RAW_2.exists()), reason="raw Schaff XML absent")
def test_metadata_distinguishes_council_and_later_western_form():
    records = parser.extract_records()

    assert records["nicene-creed-325"]["meta"]["original_publication_year"] == 325
    assert records["nicene-creed"]["meta"]["original_publication_year"] == 381
    western = records["nicene-creed-anglican-bcp-1662"]["meta"]
    assert western["original_publication_year"] == 1662
    assert "Book of Common Prayer" in western["tradition_notes"]
    assert western["provenance"]["source_url"].endswith("/creeds2.xml")


@pytest.mark.skipif(not (RAW_1.exists() and RAW_2.exists()), reason="raw Schaff XML absent")
def test_reproduction_is_pinned_and_matches_committed_outputs():
    records = parser.extract_records()

    for resource_id, record in records.items():
        provenance = record["meta"]["provenance"]
        assert provenance["download_date"] == "2026-09-17"
        assert provenance["processing_date"] == "2026-09-17"
        committed = json.loads(
            (REPO_ROOT / "data/doctrinal-documents" / f"{resource_id}.json").read_text(encoding="utf-8")
        )
        assert record == committed


@pytest.mark.skipif(not (RAW_1.exists() and RAW_2.exists()), reason="raw Schaff XML absent")
def test_write_records_syncs_collection_manifest_and_emits_receipt(tmp_path):
    data_dir = tmp_path / "data/doctrinal-documents"
    data_dir.mkdir(parents=True)
    (data_dir / "existing.json").write_text(
        json.dumps({"meta": {"id": "existing", "title": "Existing"}, "data": {"document_kind": "creed"}}),
        encoding="utf-8",
    )

    parser.write_records(parser.extract_records(), repo_root=tmp_path)

    manifest = json.loads((data_dir / "_manifest.json").read_text(encoding="utf-8"))
    assert {entry["id"] for entry in manifest["documents"]} == {
        "existing",
        "nicene-creed-325",
        "nicene-creed",
        "nicene-creed-anglican-bcp-1662",
    }
    assert manifest["stats"]["total_documents"] == 4
    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == "schaff_ecumenical_creeds_parser"
    assert "data/doctrinal-documents/_manifest.json" in receipt["data_paths"]
    assert set(receipt["allowed_field_paths"]) == {
        "/meta",
        "/data",
        "/documents",
        "/stats",
        "/last_updated",
    }
