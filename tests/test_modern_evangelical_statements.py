"""Tests for the modern evangelical statements parser."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from build.lib import writer_identities  # noqa: E402
from build.parsers import modern_evangelical_statements as parser  # noqa: E402


EFCA_FIXTURE = b"""
<html><body><ol class="articles">
  <li class="sof-grid"><h2>Article 1. God</h2><p>We believe in one God.</p></li>
  <li class="sof-grid"><h2>Article 2. The Bible</h2><p>We believe God has spoken.</p></li>
  <li class="sof-grid"><h2>Article 3. The Human Condition</h2><p>We believe humanity needs redemption.</p></li>
  <li class="sof-grid"><h2>Article 4. Jesus Christ</h2><p>We believe Jesus Christ is God incarnate.</p></li>
  <li class="sof-grid"><h2>Article 5. The Work of Christ</h2><p>We believe Christ died and rose.</p></li>
  <li class="sof-grid"><h2>Article 6. The Holy Spirit</h2><p>We believe the Spirit glorifies Christ.</p></li>
  <li class="sof-grid"><h2>Article 7. The Church</h2><p>The Lord Jesus mandated baptism and the Lord's Supper.</p></li>
  <li class="sof-grid"><h2>Article 8. Christian Living</h2><p>We believe grace bears fruit.</p></li>
  <li class="sof-grid"><h2>Article 9. Christ's Return</h2><p>We believe Christ will return.</p></li>
  <li class="sof-grid"><h2>Article 10. Response and Eternal Destiny</h2><p>We believe God will judge the world.</p></li>
</ol><footer>Site navigation must not leak.</footer></body></html>
"""


def test_extract_efca_returns_ten_numbered_articles_without_site_chrome() -> None:
    units = parser.extract_efca_statement(EFCA_FIXTURE)

    assert [unit["number"] for unit in units] == [str(n) for n in range(1, 11)]
    assert units[0] == {
        "unit_type": "article",
        "number": "1",
        "title": "God",
        "content": "We believe in one God.",
    }
    assert units[6]["title"] == "The Church"
    assert "Lord's Supper" in units[6]["content"]
    assert "Site navigation" not in " ".join(unit["content"] for unit in units)


NAE_FIXTURE = b"""
<html><body><div id="page-builder-container">
  <div class="content-row content-type container">
    <p>We believe the Bible is God's Word.</p>
    <p>We believe in one God.</p>
    <p>We believe in Jesus Christ.</p>
    <p>We believe regeneration is essential.</p>
    <p>We believe in the Spirit's present ministry.</p>
    <p>We believe in the resurrection of the saved and the lost.</p>
    <p>We believe in the spiritual unity of believers.</p>
  </div>
  <div class="content-row content-type container">
    <p><em>The NAE intentionally has not copyrighted its Statement of Faith.</em></p>
  </div>
</div></body></html>
"""


def test_extract_nae_returns_only_the_seven_belief_paragraphs() -> None:
    units = parser.extract_nae_statement(NAE_FIXTURE)

    assert [unit["number"] for unit in units] == [str(n) for n in range(1, 8)]
    assert all(unit["unit_type"] == "article" for unit in units)
    assert units[0]["title"] == "Article 1"
    combined = " ".join(unit["content"] for unit in units)
    assert "intentionally has not copyrighted" not in combined


def test_extract_nae_rejects_malformed_witness_structure() -> None:
    malformed = NAE_FIXTURE.replace(
        b"<p>We believe in the spiritual unity of believers.</p>", b""
    )

    with pytest.raises(ValueError, match="Expected 7 NAE belief paragraphs, got 6"):
        parser.extract_nae_statement(malformed)


LAUSANNE_FIXTURE = """
<html><body><div class="lop-the-content">
  <p>Christian baptism is a sign and seal of God's grace, a public declaration of new allegiance to Christ and identification with his church.</p>
  <p>In gathered worship believers see, feel and taste his grace, in Baptism and the Lord's Supper.</p>
  <p>Churches mature through regular rehearsing of the gospel in baptism and the Lord's Table.</p>
</div></body></html>
""".encode()


def test_build_lausanne_sacraments_summary_is_partial_and_not_full_text() -> None:
    units = parser.build_lausanne_sacraments_summary(LAUSANNE_FIXTURE)

    assert units == [
        {
            "unit_type": "section",
            "number": "1",
            "title": "Baptism and the Lord's Supper",
            "content": (
                "The Seoul Statement describes Christian baptism as a sign of God's "
                "grace, a public declaration of allegiance to Christ, and identification "
                "with the church. It treats Baptism and the Lord's Supper as practices "
                "through which the gathered church receives and perceives God's grace. "
                "It also calls churches to rehearse the gospel regularly through baptism "
                "and the Lord's Table."
            ),
        }
    ]
    source_text = " ".join(
        BeautifulSoup(LAUSANNE_FIXTURE, "html.parser").stripped_strings
    )
    assert units[0]["content"] not in source_text


SAMPLE_CONFIG = {
    "id": "sample-statement",
    "title": "Sample Statement",
    "author": "Sample Body",
    "original_publication_year": 2024,
    "tradition": ["evangelical", "free-church"],
    "tradition_notes": "Synthetic test document.",
    "license": "public-domain",
    "completeness": "full",
    "source": {
        "url": "https://example.test/statement",
        "format": "HTML",
        "edition": "Official HTML",
        "download_date": "2026-09-27",
        "source_hash": "sha256:" + "a" * 64,
    },
    "processing": {
        "method": "automated-with-review",
        "date": "2026-09-27",
        "notes": "Synthetic provenance.",
    },
}


def test_build_document_is_schema_valid_and_preserves_provenance() -> None:
    units = [{"unit_type": "article", "number": "1", "content": "Test content."}]
    document = parser.build_document(SAMPLE_CONFIG, units)
    schema = json.loads(
        (REPO_ROOT / "schemas/v1/doctrinal_document.schema.json").read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator(schema).validate(document)
    assert document["meta"]["tradition"] == ["evangelical", "free-church"]
    assert document["meta"]["provenance"] == {
        "source_url": "https://example.test/statement",
        "source_format": "HTML",
        "source_edition": "Official HTML",
        "download_date": "2026-09-27",
        "source_hash": "sha256:" + "a" * 64,
        "processing_method": "automated-with-review",
        "processing_script_version": parser.SCRIPT_VERSION,
        "processing_date": "2026-09-27",
        "notes": "Synthetic provenance.",
    }
    assert document["data"]["document_kind"] == "declaration"


def test_writer_identity_is_registered() -> None:
    assert writer_identities.is_authorised(parser.WRITER_IDENTITY)
    assert writer_identities.producer_type_for(parser.WRITER_IDENTITY) == "parser"


def test_verified_raw_bytes_rejects_source_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "raw/example.test/statement.html"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"<html><body>Changed witness.</body></html>")
    config = copy.deepcopy(SAMPLE_CONFIG)
    config["raw_file"] = "raw/example.test/statement.html"
    monkeypatch.setattr(parser, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="Raw witness hash mismatch for sample-statement"):
        parser._verified_raw_bytes(config)


def test_load_configs_covers_all_three_authorized_records() -> None:
    configs = parser.load_document_configs()

    assert set(configs) == {
        "efca-statement-of-faith-2019",
        "nae-statement-of-faith-current",
        "lausanne-seoul-statement-2024-sacraments-summary",
    }
    assert all(
        config["tradition"] == ["evangelical", "free-church"]
        for config in configs.values()
    )


def test_lausanne_summary_uses_its_2026_authorship_year() -> None:
    config = parser.load_document_configs()[
        "lausanne-seoul-statement-2024-sacraments-summary"
    ]

    assert config["original_publication_year"] == 2026
    assert "2024" in config["title"]
    assert "2024" in config["source"]["edition"]


def test_nae_record_represents_the_current_official_form() -> None:
    config = parser.load_document_configs()["nae-statement-of-faith-current"]
    document = parser.build_document(
        config,
        [{"unit_type": "article", "number": "1", "content": "Test."}],
    )

    assert config["title"] == "NAE Statement of Faith (Current Official Form)"
    assert config["original_publication_year"] == 1943
    assert document["data"]["revision_history"] == [
        {
            "year": 1943,
            "body": "National Association of Evangelicals",
            "description": "The NAE first adopted a Statement of Faith in 1943.",
        },
        {
            "year": 2026,
            "body": "National Association of Evangelicals",
            "description": (
                "Current official web form captured on 2026-09-27; this record does "
                "not claim that the captured wording is textually identical to the "
                "statement as adopted in 1943."
            ),
        },
    ]


def test_nae_generated_record_preserves_required_attribution_in_provenance() -> None:
    config = parser.load_document_configs()["nae-statement-of-faith-current"]
    document = parser.build_document(
        config,
        [{"unit_type": "article", "number": "1", "content": "Test."}],
    )

    assert (
        "As adopted by the National Association of Evangelicals."
        in document["meta"]["provenance"]["notes"]
    )


@pytest.mark.requires_local_artifacts
def test_cached_witnesses_match_config_hashes_and_expected_shapes() -> None:
    configs = parser.load_document_configs()
    parsed = {
        document_id: parser.parse_document(config)
        for document_id, config in configs.items()
    }

    assert len(parsed["efca-statement-of-faith-2019"]["data"]["units"]) == 10
    efca_church = parsed["efca-statement-of-faith-2019"]["data"]["units"][6]
    assert efca_church["title"] == "The Church"
    assert "two ordinances" in efca_church["content"]
    assert len(parsed["nae-statement-of-faith-current"]["data"]["units"]) == 7
    assert "spiritual unity" in parsed["nae-statement-of-faith-current"]["data"]["units"][-1]["content"]
    lausanne = parsed["lausanne-seoul-statement-2024-sacraments-summary"]
    assert lausanne["meta"]["completeness"] == "partial"
    assert lausanne["meta"]["license"] == "cc0-1.0"
    assert len(lausanne["data"]["units"]) == 1

    for document_id, expected in parsed.items():
        committed = json.loads(
            (
                REPO_ROOT
                / f"data/doctrinal-documents/{document_id}.json"
            ).read_text(encoding="utf-8")
        )
        assert committed == expected


def test_sync_manifest_removes_dangling_entries_and_adds_generated_records(tmp_path: Path) -> None:
    data_dir = tmp_path / "data/doctrinal-documents"
    data_dir.mkdir(parents=True)
    existing = build_test_document("existing", "Existing")
    (data_dir / "existing.json").write_text(json.dumps(existing), encoding="utf-8")
    old_manifest = {
        "schema_type": "doctrinal_document",
        "schema_version": "2.1.0",
        "documents": [
            {"id": "dangling", "title": "Dangling", "document_kind": "declaration", "file": "dangling.json"}
        ],
        "stats": {"total_documents": 1},
        "last_updated": "2020-01-01",
    }
    generated = {"sample-statement": parser.build_document(SAMPLE_CONFIG, [{"unit_type": "article", "number": "1", "content": "Test."}])}

    synced = parser.build_synced_manifest(
        old_manifest,
        data_dir=data_dir,
        generated_documents=generated,
        update_date="2026-09-27",
    )

    assert [entry["id"] for entry in synced["documents"]] == ["existing", "sample-statement"]
    assert synced["stats"]["total_documents"] == 2
    assert synced["last_updated"] == "2026-09-27"


def test_sync_manifest_does_not_move_last_updated_backward(tmp_path: Path) -> None:
    data_dir = tmp_path / "data/doctrinal-documents"
    data_dir.mkdir(parents=True)
    old_manifest = {
        "schema_type": "doctrinal_document",
        "schema_version": "2.1.0",
        "documents": [],
        "stats": {"total_documents": 0},
        "last_updated": "2026-10-01",
    }

    synced = parser.build_synced_manifest(
        old_manifest,
        data_dir=data_dir,
        generated_documents={"sample-statement": build_test_document("sample-statement", "Sample")},
        update_date="2026-09-27",
    )

    assert synced["last_updated"] == "2026-10-01"


def build_test_document(document_id: str, title: str) -> dict:
    config = dict(SAMPLE_CONFIG)
    config.update({"id": document_id, "title": title})
    return parser.build_document(
        config,
        [{"unit_type": "article", "number": "1", "content": "Test."}],
    )


def test_write_generated_documents_dry_run_writes_nothing(tmp_path: Path) -> None:
    documents = {"sample-statement": parser.build_document(SAMPLE_CONFIG, [{"unit_type": "article", "number": "1", "content": "Test."}])}

    parser.write_generated_documents(
        documents,
        repo_root=tmp_path,
        update_date="2026-09-27",
        dry_run=True,
    )

    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "review").exists()


def test_dry_run_rejects_schema_invalid_config_value_before_reporting_success(
    tmp_path: Path,
) -> None:
    config = copy.deepcopy(SAMPLE_CONFIG)
    config["license"] = "all-rights-reserved"
    document = parser.build_document(
        config,
        [{"unit_type": "article", "number": "1", "content": "Test."}],
    )

    with pytest.raises(ValidationError, match="all-rights-reserved"):
        parser.write_generated_documents(
            {"sample-statement": document},
            repo_root=tmp_path,
            update_date="2026-09-27",
            dry_run=True,
        )

    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "review").exists()


def test_write_rejects_schema_invalid_document_before_creating_artifacts(
    tmp_path: Path,
) -> None:
    document = parser.build_document(
        SAMPLE_CONFIG,
        [{"unit_type": "article", "number": "1", "content": "Test."}],
    )
    document["data"]["units"] = []

    with pytest.raises(ValidationError, match="should be non-empty"):
        parser.write_generated_documents(
            {"sample-statement": document},
            repo_root=tmp_path,
            update_date="2026-09-27",
            dry_run=False,
        )

    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "review").exists()


def test_write_generated_documents_emits_records_manifest_and_writer_receipt(tmp_path: Path) -> None:
    document = parser.build_document(
        SAMPLE_CONFIG,
        [{"unit_type": "article", "number": "1", "content": "Test."}],
    )

    parser.write_generated_documents(
        {"sample-statement": document},
        repo_root=tmp_path,
        update_date="2026-09-27",
        dry_run=False,
    )

    record_path = tmp_path / "data/doctrinal-documents/sample-statement.json"
    manifest_path = tmp_path / "data/doctrinal-documents/_manifest.json"
    assert json.loads(record_path.read_text(encoding="utf-8")) == document
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in manifest["documents"]] == ["sample-statement"]
    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == parser.WRITER_IDENTITY
    assert receipt["data_paths"] == [
        "data/doctrinal-documents/_manifest.json",
        "data/doctrinal-documents/sample-statement.json",
    ]
    assert all(
        entry["after_sha256"]
        for entry in receipt["checksums"].values()
    )


@pytest.mark.requires_local_artifacts
def test_main_all_dry_run_parses_three_documents_without_writing(monkeypatch) -> None:
    call: dict = {}

    def capture(documents, *, repo_root, update_date, dry_run):
        call.update(
            documents=documents,
            repo_root=repo_root,
            update_date=update_date,
            dry_run=dry_run,
        )

    monkeypatch.setattr(parser, "write_generated_documents", capture)

    assert parser.main(["--all", "--dry-run"]) == 0
    assert set(call["documents"]) == set(parser.DOCUMENT_IDS)
    assert call["repo_root"] == parser.REPO_ROOT
    assert call["update_date"] == "2026-09-27"
    assert call["dry_run"] is True


def test_main_does_not_report_validated_when_document_fails_schema_validation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = copy.deepcopy(SAMPLE_CONFIG)
    config["id"] = "efca-statement-of-faith-2019"
    invalid_document = parser.build_document(config, [])
    monkeypatch.setattr(
        parser,
        "load_document_configs",
        lambda: {"efca-statement-of-faith-2019": config},
    )
    monkeypatch.setattr(parser, "parse_document", lambda _config: invalid_document)

    with pytest.raises(ValidationError, match="should be non-empty"):
        parser.main(["--document", "efca-statement-of-faith-2019", "--dry-run"])

    assert "validated" not in capsys.readouterr().out


def test_committed_records_validate_against_doctrinal_schema() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/v1/doctrinal_document.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)

    for document_id in parser.DOCUMENT_IDS:
        path = REPO_ROOT / f"data/doctrinal-documents/{document_id}.json"
        validator.validate(json.loads(path.read_text(encoding="utf-8")))


def test_doctrinal_manifest_matches_files_and_declared_total() -> None:
    data_dir = REPO_ROOT / "data/doctrinal-documents"
    actual_files = {
        path.name for path in data_dir.glob("*.json") if path.name != "_manifest.json"
    }
    manifest = json.loads((data_dir / "_manifest.json").read_text(encoding="utf-8"))
    manifest_files = {entry["file"] for entry in manifest["documents"]}

    assert manifest_files == actual_files
    assert manifest["stats"]["total_documents"] == len(actual_files)
