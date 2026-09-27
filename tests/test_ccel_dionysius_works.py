import json
from pathlib import Path

import pytest

from build.parsers import ccel_dionysius_works as parser

RAW = Path(__file__).resolve().parents[1] / "raw" / "ccel" / "dionysius-works.xml"


@pytest.mark.skipif(not RAW.exists(), reason="raw Pseudo-Dionysius XML absent")
def test_parses_both_volumes_of_parker_dionysius():
    record = parser.build_record()
    assert record["meta"]["completeness"] == "full"
    assert record["meta"]["provenance"]["source_hash"].startswith("sha256:")
    sections = record["data"]["sections"]
    titles = " ".join(str(section.get("title", "")) for section in sections)
    assert "Volume 1" in titles
    assert "Volume 2" in titles
    text = str(sections)
    assert "Divine Names" in text
    assert "Heavenly Hierarchy" in text
    assert "Ecclesiastical Hierarchy" in text


@pytest.mark.skipif(not RAW.exists(), reason="raw Pseudo-Dionysius XML absent")
def test_reproduction_is_pinned_and_matches_committed_output():
    record = parser.build_record()
    provenance = record["meta"]["provenance"]
    assert provenance["download_date"] == "2026-09-17"
    assert provenance["processing_date"] == "2026-09-17"
    committed = json.loads(
        (Path(__file__).resolve().parents[1] / "data/structured-text/pseudo-dionysius-works-parker.json").read_text(encoding="utf-8")
    )
    assert record == committed


@pytest.mark.skipif(not RAW.exists(), reason="raw Pseudo-Dionysius XML absent")
def test_write_record_emits_registered_writer_receipt(tmp_path):
    parser.write_record(parser.build_record(), repo_root=tmp_path)

    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == "ccel_dionysius_works_parser"
    assert receipt["data_paths"] == ["data/structured-text/pseudo-dionysius-works-parker.json"]
