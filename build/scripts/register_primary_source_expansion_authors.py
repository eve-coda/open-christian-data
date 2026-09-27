"""Register authors and corporate attributions used by the primary-source expansion."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from build.lib import writer_manifest
from build.lib.corpus_writer import write_json
from build.lib.paths import REPO_ROOT

WRITER_IDENTITY = "primary_source_expansion_author_registry"
SCRIPT_VERSION = "build/scripts/register_primary_source_expansion_authors.py@v1.0.0"
REGISTRY_PATH = REPO_ROOT / "data" / "authors" / "registry.json"

NEW_AUTHORS = (
    {
        "author_id": "anonymous",
        "display_name": "Anonymous",
        "aliases": ["Unknown author"],
        "birth_year": None,
        "death_year": None,
        "tradition": ["ecumenical"],
        "nationality": None,
        "works": ["cloud-of-unknowing"],
        "notes": "Generic attribution for works whose author is unknown; not a single historical person.",
    },
    {
        "author_id": "bonaventure",
        "display_name": "Bonaventure",
        "aliases": ["Saint Bonaventure", "Bonaventure of Bagnoregio", "Doctor Seraphicus"],
        "birth_year": 1217,
        "death_year": 1274,
        "tradition": ["catholic", "scholastic"],
        "nationality": "Italian",
        "works": ["bonaventure-opera-omnia-vol-5"],
        "notes": "Franciscan theologian, cardinal, and Doctor of the Church; birth year is approximate.",
    },
    {
        "author_id": "council-of-trent",
        "display_name": "Council of Trent",
        "aliases": ["Concilium Tridentinum"],
        "birth_year": None,
        "death_year": None,
        "tradition": ["catholic", "confessional"],
        "nationality": None,
        "works": ["roman-catechism-1829"],
        "notes": "Roman Catholic ecumenical council held from 1545 to 1563; corporate attribution for the Roman Catechism.",
    },
    {
        "author_id": "first-council-of-nicaea",
        "display_name": "First Council of Nicaea",
        "aliases": ["Council of Nicaea (325)", "First Ecumenical Council"],
        "birth_year": None,
        "death_year": None,
        "tradition": ["ecumenical", "patristic"],
        "nationality": None,
        "works": ["nicene-creed-325"],
        "notes": "The first ecumenical council, convened in 325; corporate attribution for the original Nicene Creed.",
    },
    {
        "author_id": "jacobus-arminius",
        "display_name": "Jacobus Arminius",
        "aliases": ["James Arminius", "Jakob Hermanszoon", "Jacob Harmenszoon"],
        "birth_year": 1560,
        "death_year": 1609,
        "tradition": ["arminian", "reformed"],
        "nationality": "Dutch",
        "works": ["arminius-works-vol-1", "arminius-works-vol-2", "arminius-works-vol-3"],
        "notes": "Dutch Reformed theologian whose teaching gave rise to the Remonstrant tradition.",
    },
    {
        "author_id": "john-duns-scotus",
        "display_name": "John Duns Scotus",
        "aliases": ["Duns Scotus", "Joannes Duns Scotus", "Doctor Subtilis"],
        "birth_year": 1266,
        "death_year": 1308,
        "tradition": ["catholic", "scholastic"],
        "nationality": "Scottish",
        "works": ["duns-scotus-opera-omnia-vol-8"],
        "notes": "Franciscan scholastic theologian and philosopher; birth year is approximate.",
    },
    {
        "author_id": "julian-of-norwich",
        "display_name": "Julian of Norwich",
        "aliases": ["Dame Julian of Norwich"],
        "birth_year": 1343,
        "death_year": 1416,
        "tradition": ["catholic", "monastic"],
        "nationality": "English",
        "works": ["julian-revelations-divine-love"],
        "notes": "English anchoress and mystic; both dates are approximate and the death year is a terminus post quem.",
    },
    {
        "author_id": "peter-lombard",
        "display_name": "Peter Lombard",
        "aliases": ["Petrus Lombardus", "Master of the Sentences"],
        "birth_year": 1096,
        "death_year": 1160,
        "tradition": ["catholic", "scholastic"],
        "nationality": "Italian",
        "works": ["peter-lombard-sentences-1841-vols-1-2", "peter-lombard-sentences-1841-vols-3-4"],
        "notes": "Scholastic theologian and bishop of Paris; dates are approximate.",
    },
    {
        "author_id": "philipp-melanchthon",
        "display_name": "Philipp Melanchthon",
        "aliases": ["Philip Melanchthon", "Philipp Schwartzerdt"],
        "birth_year": 1497,
        "death_year": 1560,
        "tradition": ["lutheran", "confessional"],
        "nationality": "German",
        "works": ["apology-augsburg-confession", "power-primacy-pope"],
        "notes": "German reformer and principal author of several Lutheran confessional documents.",
    },
    {
        "author_id": "church-of-england",
        "display_name": "Church of England",
        "aliases": ["Ecclesia Anglicana"],
        "birth_year": None,
        "death_year": None,
        "tradition": ["ecumenical"],
        "nationality": None,
        "works": ["nicene-creed-anglican-bcp-1662"],
        "notes": "Corporate attribution for the 1662 Book of Common Prayer witness of the Niceno-Constantinopolitan Creed.",
    },
)

ALIASES_BY_ID = {
    "hippolytus-of-rome": ("Hippolytus of Rome (attributed)",),
}
WORKS_BY_ID = {
    "hippolytus-of-rome": ("apostolic-tradition-easton-1934",),
    "schaff-philip": (
        "creeds-of-christendom-vol-1",
        "creeds-of-christendom-vol-2",
        "creeds-of-christendom-vol-3",
    ),
    "pseudo-dionysius-the-areopagite": ("pseudo-dionysius-works-parker",),
    "benedict-of-nursia": ("rule-of-benedict-1906",),
    "philipp-melanchthon": ("smalcald-articles",),
    "martin-luther": ("smalcald-articles",),
}
OBSOLETE_AUTHOR_IDS = frozenset({"western-church"})


def build_registry(registry: dict) -> dict:
    updated = copy.deepcopy(registry)
    authors = updated["authors"]
    authors[:] = [author for author in authors if author["author_id"] not in OBSOLETE_AUTHOR_IDS]
    by_id = {author["author_id"]: author for author in authors}
    for entry in NEW_AUTHORS:
        if entry["author_id"] not in by_id:
            copied = copy.deepcopy(entry)
            authors.append(copied)
            by_id[copied["author_id"]] = copied
    for author_id, aliases in ALIASES_BY_ID.items():
        author = by_id.get(author_id)
        if author is None:
            continue
        for alias in aliases:
            if alias not in author["aliases"]:
                author["aliases"].append(alias)
    for author_id, works in WORKS_BY_ID.items():
        author = by_id.get(author_id)
        if author is None:
            continue
        for work in works:
            if work not in author["works"]:
                author["works"].append(work)
    authors.sort(key=lambda author: author["author_id"])
    return updated


def write_registry(*, repo_root: Path = REPO_ROOT) -> None:
    path = repo_root / "data" / "authors" / "registry.json"
    previous = json.loads(path.read_text(encoding="utf-8"))
    updated = build_registry(previous)
    entries_changed, fields_changed = writer_manifest.diff_counts(
        {"meta": {}, "data": previous["authors"]},
        {"meta": {}, "data": updated["authors"]},
        key=lambda author: author["author_id"],
    )
    with writer_manifest.run(
        writer_identity=WRITER_IDENTITY,
        writer_version=SCRIPT_VERSION,
        data_paths=[path],
        allowed_field_paths=("/authors",),
        repo_root=repo_root,
        manifests_dir=repo_root / "review" / "writer-manifests",
    ) as manifest_run:
        write_json(path, updated)
        manifest_run.record_delta(
            path,
            entries_changed=entries_changed,
            fields_changed=fields_changed,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    write_registry()
    print(f"Registered {len(NEW_AUTHORS)} expansion authors plus attribution aliases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
