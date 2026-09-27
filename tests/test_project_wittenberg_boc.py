import json
import unicodedata
from pathlib import Path

import pytest

from build.parsers import project_wittenberg_boc as parser

RAW = Path(__file__).resolve().parents[1] / "raw" / "project-wittenberg" / "boc"


@pytest.mark.skipif(not RAW.exists(), reason="raw Project Wittenberg files absent")
def test_builds_three_missing_book_of_concord_documents():
    records = parser.build_records()

    assert set(records) == {
        "apology-augsburg-confession",
        "smalcald-articles",
        "power-primacy-pope",
    }
    assert len(records["apology-augsburg-confession"]["data"]["sections"]) == 38
    assert len(records["smalcald-articles"]["data"]["sections"]) == 22
    primacy_blocks = records["power-primacy-pope"]["data"]["sections"][0]["content_blocks"]
    assert "Roman Pontiff claims" in " ".join(primacy_blocks)


@pytest.mark.skipif(not RAW.exists(), reason="raw Project Wittenberg files absent")
def test_searchable_content_rejects_replacement_and_control_characters():
    records = parser.build_records()

    for resource_id, record in records.items():
        for section in record["data"]["sections"]:
            searchable_text = " ".join([section["title"], *section["content_blocks"]])
            forbidden = [
                character
                for character in searchable_text
                if character == "\ufffd" or unicodedata.category(character) == "Cc"
            ]
            assert forbidden == [], f"{resource_id} contains {forbidden!r}"


@pytest.mark.parametrize(
    "footer_fragment",
    [
        "Rev. Robert E. Smith",
        "of the Walther Library",
        "Surface Mail: 6600 N. Clinton St.",
        "E-mail: smithre@mail.ctsfw.edu",
        "Email: smithre@mail.ctsfw.edu",
        "USA Phone: (219) 452-3149",
        "Fax: (219) 452-2126",
        "ments or suggestions to:",
    ],
)
def test_partial_project_wittenberg_contact_footer_is_removed(tmp_path, footer_fragment):
    source = tmp_path / "partial-footer.asc"
    source.write_text(
        f"Theological text remains.\n\n{footer_fragment}\ncontact details follow\n",
        encoding="utf-8",
    )

    assert parser._paragraphs(source) == ["Theological text remains."]


@pytest.mark.skipif(not RAW.exists(), reason="raw Project Wittenberg files absent")
def test_corrupt_contact_insertion_is_removed_without_dropping_following_theology():
    apology = parser.build_records()["apology-augsburg-confession"]
    text = " ".join(
        block
        for section in apology["data"]["sections"]
        for block in section["content_blocks"]
    )

    assert "which is properly the promise of the remission of sins" in text
    assert "the doctrine of our adversaries. Hence we find fault" in text
    assert "Christ'ments" not in text
    assert "Robert E. Smith" not in text
    assert "Walther Library" not in text
    assert "Surface Mail" not in text
    assert "smithre@mail.ctsfw.edu" not in text


@pytest.mark.skipif(not RAW.exists(), reason="raw Project Wittenberg files absent")
def test_repeated_project_wittenberg_boilerplate_is_only_in_provenance():
    records = parser.build_records()
    notice = (
        "This text was converted to ascii format for Project Wittenberg by Allen "
        "Mulvey and is in the public domain. You may freely distribute, copy or "
        "print this text. Please direct any comments or suggestions to: Rev. Robert "
        "E. Smith of the Walther Library at Concordia Theological Seminary."
    )

    for record in records.values():
        content = json.dumps(record["data"]["sections"], ensure_ascii=False)
        notes = record["meta"]["provenance"]["notes"]
        assert "converted to ascii format for Project Wittenberg" not in content
        assert "You may freely distribute, copy or print this text" not in content
        assert notes.count(notice) == 1


@pytest.mark.skipif(not RAW.exists(), reason="raw Project Wittenberg files absent")
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


@pytest.mark.skipif(not RAW.exists(), reason="raw Project Wittenberg files absent")
def test_write_records_emits_registered_writer_receipt(tmp_path):
    record = parser.build_records()["power-primacy-pope"]

    parser.write_records({"power-primacy-pope": record}, repo_root=tmp_path)

    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == "project_wittenberg_boc_parser"
    assert receipt["data_paths"] == ["data/structured-text/power-primacy-pope.json"]
