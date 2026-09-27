from __future__ import annotations

import json
from pathlib import Path

from build.scripts import register_primary_source_expansion_authors as registry_writer


EXPECTED_NAMES = {
    "Anonymous",
    "Bonaventure",
    "Council of Trent",
    "First Council of Nicaea",
    "Hippolytus of Rome (attributed)",
    "Jacobus Arminius",
    "John Duns Scotus",
    "Julian of Norwich",
    "Peter Lombard",
    "Philipp Melanchthon",
    "Church of England",
}


def _known_names(registry: dict) -> set[str]:
    return {
        name
        for author in registry["authors"]
        for name in [author["display_name"], *author.get("aliases", [])]
    }


def test_expansion_authors_and_aliases_are_registered_idempotently():
    registry_path = Path(__file__).resolve().parents[1] / "data/authors/registry.json"
    original = json.loads(registry_path.read_text(encoding="utf-8"))

    once = registry_writer.build_registry(original)
    twice = registry_writer.build_registry(once)

    assert EXPECTED_NAMES <= _known_names(once)
    assert twice == once
    ids = [author["author_id"] for author in once["authors"]]
    assert len(ids) == len(set(ids))


def test_existing_author_entries_receive_all_expansion_backlinks():
    registry_path = Path(__file__).resolve().parents[1] / "data/authors/registry.json"
    original = json.loads(registry_path.read_text(encoding="utf-8"))
    updated = registry_writer.build_registry(original)
    by_id = {author["author_id"]: author for author in updated["authors"]}

    expected = {
        "schaff-philip": {
            "creeds-of-christendom-vol-1",
            "creeds-of-christendom-vol-2",
            "creeds-of-christendom-vol-3",
        },
        "pseudo-dionysius-the-areopagite": {"pseudo-dionysius-works-parker"},
        "benedict-of-nursia": {"rule-of-benedict-1906"},
        "philipp-melanchthon": {"smalcald-articles"},
        "martin-luther": {"smalcald-articles"},
    }
    for author_id, work_ids in expected.items():
        assert work_ids <= set(by_id[author_id]["works"])


def test_obsolete_western_church_witness_registry_entry_is_not_created():
    registry_path = Path(__file__).resolve().parents[1] / "data/authors/registry.json"
    updated = registry_writer.build_registry(json.loads(registry_path.read_text(encoding="utf-8")))

    assert "western-church" not in {author["author_id"] for author in updated["authors"]}
    church_of_england = next(
        author for author in updated["authors"] if author["author_id"] == "church-of-england"
    )
    assert "nicene-creed-anglican-bcp-1662" in church_of_england["works"]


def test_registry_writer_emits_registered_receipt(tmp_path):
    registry_path = tmp_path / "data/authors/registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({"authors": []}), encoding="utf-8")

    registry_writer.write_registry(repo_root=tmp_path)

    receipts = list((tmp_path / "review/writer-manifests").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["writer_identity"] == "primary_source_expansion_author_registry"
    assert receipt["data_paths"] == ["data/authors/registry.json"]
    assert receipt["allowed_field_paths"] == ["/authors"]
