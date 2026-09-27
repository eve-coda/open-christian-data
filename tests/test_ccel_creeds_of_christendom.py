"""Tests for ccel_creeds_of_christendom.py.

Schaff's "The Creeds of Christendom, Vol. I: The History of Creeds" (CCEL ThML)
parsed into the structured_text schema. The ThML nests div1 (chapter) > div2
(section) > div3 (subsection); the parser must recurse all three levels and skip
front/back matter (Title Page, Prefatory, Indexes).

Integration tests are skipped when the raw CCEL XML is absent (gitignored raw/).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ocd_kernel.lib.schema_enums import get_enum  # noqa: E402
from build.parsers import ccel_creeds_of_christendom as cc  # noqa: E402

RAW = REPO_ROOT / "raw" / "ccel" / "schaff" / "creeds1.xml"


def _walk(sections):
    for s in sections:
        yield s
        yield from _walk(s.get("children", []))


def test_config_enums_are_schema_valid():
    assert set(cc.WORK_META["tradition"]) <= get_enum("structured_text", "meta", "tradition")
    assert cc.WORK_KIND in get_enum("structured_text", "data", "work_kind")
    assert cc.WORK_META["era"] in get_enum("structured_text", "meta", "era")
    assert cc.WORK_META["audience"] in get_enum("structured_text", "meta", "audience")


@pytest.mark.skipif(not RAW.exists(), reason="raw creeds1.xml not present")
def test_parses_eight_content_chapters():
    data = cc.parse_creeds_volume()
    chapters = data["sections"]
    assert len(chapters) == 8, f"expected 8 content chapters, got {len(chapters)}"
    for ch in chapters:
        assert ch["section_type"] == "chapter"
        assert ch["title"], f"chapter missing title: {ch.get('label')}"
    titles = " ".join((ch.get("title") or "") for ch in chapters).lower()
    assert "index" not in titles
    assert "title page" not in titles
    assert "prefatory" not in titles


@pytest.mark.skipif(not RAW.exists(), reason="raw creeds1.xml not present")
def test_chapter_two_has_section_children():
    data = cc.parse_creeds_volume()
    ch2 = next(
        c for c in data["sections"] if "cumenical" in (c.get("title") or "").lower()
    )
    assert ch2["children"], "Chapter 2 should have section children"
    assert all(s["section_type"] == "section" for s in ch2["children"])
    # one of the sections is the Apostles' Creed discussion
    sec_titles = " ".join((s.get("title") or "") for s in ch2["children"]).lower()
    assert "apostles" in sec_titles


@pytest.mark.skipif(not RAW.exists(), reason="raw creeds1.xml not present")
def test_div3_becomes_subsection():
    data = cc.parse_creeds_volume()
    types = {s["section_type"] for s in _walk(data["sections"])}
    # creeds1.xml has 49 div3 elements; recursion must surface them as subsections
    assert "subsection" in types


@pytest.mark.skipif(not RAW.exists(), reason="raw creeds1.xml not present")
def test_section_shape():
    data = cc.parse_creeds_volume()
    for s in _walk(data["sections"]):
        assert isinstance(s["content_blocks"], list)
        assert all(isinstance(b, str) for b in s["content_blocks"])
        assert isinstance(s["scripture_references"], list)
        assert isinstance(s["word_count"], int)


@pytest.mark.skipif(
    not (REPO_ROOT / "data" / "structured-text" / "creeds-of-christendom-vol-1.json").exists(),
    reason="output not yet generated",
)
def test_output_top_section_count():
    path = REPO_ROOT / "data" / "structured-text" / "creeds-of-christendom-vol-1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["data"]["sections"]) == 8


@pytest.mark.parametrize(
    ("volume", "expected_titles"),
    [
        (2, ("Scripture Confessions", "Greek and Russian Symbols")),
        (
            3,
            (
                "Part First. The Creeds of the Evangelical Lutheran Churches",
                "Part Second. The Creeds of the Evangelical Reformed Churches",
            ),
        ),
    ],
)
def test_additional_volumes_parse_content_and_skip_indexes(volume, expected_titles):
    raw = REPO_ROOT / "raw" / "ccel" / "schaff" / f"creeds{volume}.xml"
    if not raw.exists():
        pytest.skip(f"raw creeds{volume}.xml not present")

    data = cc.parse_creeds_volume(volume)
    titles = [section.get("title") for section in data["sections"]]

    for title in expected_titles:
        assert title in titles
    assert "Title Page" not in titles
    assert not any("Index" in (title or "") for title in titles)
    assert data["work_id"] == f"creeds-of-christendom-vol-{volume}"


@pytest.mark.parametrize("volume, expected_count", [(1, 8), (2, 6), (3, 4)])
def test_each_volume_has_the_documented_top_level_scope(volume, expected_count):
    raw = REPO_ROOT / "raw" / "ccel" / "schaff" / f"creeds{volume}.xml"
    if not raw.exists():
        pytest.skip(f"raw creeds{volume}.xml not present")

    data = cc.parse_creeds_volume(volume)

    assert len(data["sections"]) == expected_count
    if volume == 3:
        titles = [section["title"] for section in data["sections"]]
        assert titles[0] == "Part First. The Creeds of the Evangelical Lutheran Churches"
        assert "Original Table of Contents" not in titles


@pytest.mark.parametrize("volume", [1, 2, 3])
def test_volume_metadata_and_config_name_identical_sixth_edition(volume, tmp_path):
    meta = cc.build_meta(volume, "sha256:abc")
    config_path = cc.write_source_config(volume, "sha256:abc", repo_root=tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert meta["id"] == f"creeds-of-christendom-vol-{volume}"
    assert "sixth edition" in meta["provenance"]["source_edition"].lower()
    assert "revised and enlarged by David S. Schaff" in meta["provenance"]["source_edition"]
    assert "1931" in meta["provenance"]["source_edition"]
    assert config["source_edition"] == meta["provenance"]["source_edition"]
    assert {tuple(item.values()) for item in meta["contributors"]} >= {
        ("David S. Schaff", "reviser"),
    }
    notes = meta["provenance"]["notes"]
    assert "1931 Preface to the Sixth Edition" in notes
    assert "excluded" in notes
    assert "United States" in notes
    assert "1877, 1905, and 1919" in notes


@pytest.mark.parametrize("volume", [1, 2, 3])
def test_non_public_domain_1931_preface_is_not_searchable_content(volume):
    raw = REPO_ROOT / "raw" / "ccel" / "schaff" / f"creeds{volume}.xml"
    if not raw.exists():
        pytest.skip(f"raw creeds{volume}.xml not present")

    data = cc.parse_creeds_volume(volume)
    searchable = json.dumps(data["sections"], ensure_ascii=False)

    assert "PREFACE TO THE SIXTH EDITION" not in searchable.upper()
    assert "Since the appearance of the Creeds of Christendom, 1877" not in searchable


@pytest.mark.parametrize("volume", [1, 2, 3])
def test_reproduction_is_pinned_and_matches_committed_output(volume):
    raw = REPO_ROOT / "raw" / "ccel" / "schaff" / f"creeds{volume}.xml"
    if not raw.exists():
        pytest.skip(f"raw creeds{volume}.xml not present")

    data = cc.parse_creeds_volume(volume)
    source_hash = data.pop("_source_hash")
    envelope = {"meta": cc.build_meta(volume, source_hash), "data": data}
    assert envelope["meta"]["provenance"]["download_date"] == "2026-09-17"
    assert envelope["meta"]["provenance"]["processing_date"] == "2026-09-17"
    committed = json.loads(
        (REPO_ROOT / "data/structured-text" / f"creeds-of-christendom-vol-{volume}.json").read_text(encoding="utf-8")
    )
    assert envelope == committed


def test_write_output_emits_registered_writer_receipt(tmp_path):
    if not RAW.exists():
        pytest.skip("raw creeds1.xml not present")
    data = cc.parse_creeds_volume(1)

    cc.write_output(1, data, repo_root=tmp_path)

    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == "ccel_creeds_of_christendom_parser"
    assert receipt["data_paths"] == ["data/structured-text/creeds-of-christendom-vol-1.json"]
