import json
from pathlib import Path

import pytest

from build.parsers import ccel_arminius_works as parser

RAW = Path(__file__).resolve().parents[1] / "raw" / "ccel" / "arminius"


@pytest.mark.skipif(not all((RAW / f"works{volume}.xml").exists() for volume in (1, 2, 3)), reason="raw Arminius XML absent")
def test_parses_three_public_domain_arminius_volumes():
    records = parser.build_records()
    assert set(records) == {"arminius-works-vol-1", "arminius-works-vol-2", "arminius-works-vol-3"}
    titles = " ".join(
        section.get("title") or ""
        for section in records["arminius-works-vol-1"]["data"]["sections"]
    )
    assert "Declaration Of The Sentiments" in titles


@pytest.mark.skipif(not all((RAW / f"works{volume}.xml").exists() for volume in (1, 2, 3)), reason="raw Arminius XML absent")
def test_reproduction_is_pinned_and_matches_committed_outputs():
    records = parser.build_records()

    for resource_id, record in records.items():
        assert record["meta"]["provenance"]["download_date"] == "2026-09-17"
        assert record["meta"]["provenance"]["processing_date"] == "2026-09-17"
        committed = json.loads(
            (Path(__file__).resolve().parents[1] / "data/structured-text" / f"{resource_id}.json").read_text(encoding="utf-8")
        )
        assert record == committed


@pytest.mark.skipif(not all((RAW / f"works{volume}.xml").exists() for volume in (1, 2, 3)), reason="raw Arminius XML absent")
def test_write_records_emits_registered_writer_receipt(tmp_path):
    record = parser.build_records()["arminius-works-vol-1"]

    parser.write_records({"arminius-works-vol-1": record}, repo_root=tmp_path)

    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == "ccel_arminius_works_parser"
    assert receipt["data_paths"] == ["data/structured-text/arminius-works-vol-1.json"]
