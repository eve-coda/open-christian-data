"""Build structured records for a provenance-controlled public-domain expansion."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build.lib import writer_manifest
from build.lib.corpus_writer import envelope_delta_counts, load_json, write_json

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "public-domain-expansion"
OUT = ROOT / "data" / "structured-text"
SOURCES = ROOT / "sources" / "structured-text"
MAX_CHARS = 6000
PROVENANCE_DATE = "2026-09-17"
WRITER_IDENTITY = "public_domain_expansion_parser"
SCRIPT_VERSION = "build/parsers/public_domain_expansion.py@v1.0.0"
GUTENBERG_JURISDICTION_NOTICE = (
    "This eBook is for the use of anyone anywhere in the United States and most "
    "other parts of the world at no cost and with almost no restrictions whatsoever. "
    "You may copy it, give it away or re-use it under the terms of the Project "
    "Gutenberg License included with this eBook or online at www.gutenberg.org. "
    "If you are not located in the United States, you will have to check the laws "
    "of the country where you are located before using this eBook."
)
OUTSIDE_US_NOTICE = "Downstream users outside the United States must check local law."

SPEC_DEFAULTS = {
    "roman-catechism-1829": {
        "raw_filename": "roman-catechism-1829.txt",
        "original_publication_year": 1566,
        "language": "en",
        "original_language": "la",
        "tradition": ["catholic"],
        "contributors": [{"name": "Jeremiah Donovan", "role": "translator"}],
    },
    "rule-of-benedict-1906": {
        "raw_filename": "rule-benedict-1906.txt",
        "original_publication_year": 530,
        "language": "en",
        "original_language": "la",
        "tradition": ["monastic"],
        "contributors": [
            {"name": "Oswald Hunter Blair", "role": "translator"},
            {"name": "Oswald Hunter Blair", "role": "editor"},
        ],
    },
    "apostolic-tradition-easton-1934": {
        "raw_filename": "apostolic-tradition-easton-pg61614.txt",
        "original_publication_year": 215,
        "language": "en",
        "original_language": "grc",
        "tradition": ["patristic"],
        "contributors": [{"name": "Burton Scott Easton", "role": "translator"}],
    },
    "peter-lombard-sentences-1841-vols-1-2": {
        "raw_filename": "peter-lombard-1841-vol1-2.txt",
        "original_publication_year": 1152,
        "language": "la",
        "original_language": "la",
        "tradition": ["catholic"],
        "contributors": [],
    },
    "peter-lombard-sentences-1841-vols-3-4": {
        "raw_filename": "peter-lombard-1841-vol3-4.txt",
        "original_publication_year": 1152,
        "language": "la",
        "original_language": "la",
        "tradition": ["catholic"],
        "contributors": [],
    },
    "bonaventure-opera-omnia-vol-5": {
        "raw_filename": "bonaventure-opera-vol5-1891.txt",
        "original_publication_year": 1274,
        "language": "la",
        "original_language": "la",
        "tradition": ["catholic"],
        "contributors": [
            {"name": "Collegium S. Bonaventura", "role": "editor"},
        ],
    },
    "duns-scotus-opera-omnia-vol-8": {
        "raw_filename": "duns-scotus-opera-vol8-1891.txt",
        "original_publication_year": 1305,
        "language": "la",
        "original_language": "la",
        "tradition": ["scholastic"],
        "contributors": [
            {"name": "Luke Wadding", "role": "editor"},
            {"name": "Franciscan Fathers of the Observance", "role": "reviser"},
        ],
    },
    "julian-revelations-divine-love": {
        "raw_filename": "julian-revelations-pg52958.txt",
        "original_publication_year": 1395,
        "language": "en",
        "original_language": "enm",
        "tradition": ["monastic"],
        "contributors": [{"name": "Grace Warrack", "role": "editor"}],
    },
    "cloud-of-unknowing": {
        "raw_filename": "cloud-unknowing.txt",
        "original_publication_year": 1375,
        "language": "en",
        "original_language": "enm",
        "tradition": ["monastic"],
        "contributors": [{"name": "Evelyn Underhill", "role": "editor"}],
    },
}


def _read_config(resource_id: str) -> dict:
    """Load source-controlled metadata, filling fields only for pre-migration configs."""
    config_path = SOURCES / resource_id / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for key, value in SPEC_DEFAULTS[resource_id].items():
        config.setdefault(key, value)
    return config


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    start = re.search(r"^\*\*\*\s*START OF.*$", text, re.MULTILINE | re.IGNORECASE)
    end = re.search(r"^\*\*\*\s*END OF.*$", text, re.MULTILINE | re.IGNORECASE)
    if start and end and start.end() < end.start():
        text = text[start.end() : end.start()]
    return text


def _sections(path: Path) -> list[dict]:
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", _body(path))]
    paragraphs = [p for p in paragraphs if p]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        while len(paragraph) > MAX_CHARS:
            cut = paragraph.rfind(" ", 0, MAX_CHARS)
            cut = cut if cut > 0 else MAX_CHARS
            if current:
                chunks.append("\n\n".join(current)); current=[]; size=0
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if current and size + len(paragraph) + 2 > MAX_CHARS:
            chunks.append("\n\n".join(current)); current=[]; size=0
        if paragraph:
            current.append(paragraph); size += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    return [
        {"section_type": "section", "label": f"Passage {i}", "title": None, "content_blocks": [chunk], "scripture_references": [], "word_count": len(chunk.split()), "children": []}
        for i, chunk in enumerate(chunks, 1)
    ]


def build_records() -> dict[str, dict]:
    records = {}
    for resource_id in SPEC_DEFAULTS:
        config = _read_config(resource_id)
        path = RAW / config["raw_filename"]
        raw = path.read_bytes()
        year = config["original_publication_year"]
        provenance = {
            key: config[key]
            for key in (
                "source_url",
                "source_format",
                "source_edition",
                "download_date",
                "processing_method",
                "processing_script_version",
                "processing_date",
                "notes",
            )
        }
        provenance["source_hash"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        if "gutenberg.org" in provenance["source_url"]:
            notes = provenance["notes"]
            if GUTENBERG_JURISDICTION_NOTICE not in notes:
                notes = f"{notes} {GUTENBERG_JURISDICTION_NOTICE}"
            if OUTSIDE_US_NOTICE not in notes:
                notes = f"{notes} {OUTSIDE_US_NOTICE}"
            provenance["notes"] = notes
        records[resource_id] = {
            "meta": {
                "id": resource_id,
                "title": config["title"],
                "author": config["author"],
                "author_birth_year": None,
                "author_death_year": None,
                "contributors": config["contributors"],
                "original_publication_year": year,
                "language": config["language"],
                "original_language": config["original_language"],
                "tradition": config["tradition"],
                "tradition_notes": "Historical primary source in a public-domain edition.",
                "era": "patristic" if year < 800 else ("medieval" if year < 1500 else "reformation"),
                "audience": "scholarly",
                "license": config["license"],
                "schema_type": config["schema_type"],
                "schema_version": "2.1.0",
                "completeness": "full",
                "provenance": provenance,
            },
            "data": {
                "work_id": resource_id,
                "work_kind": "theological-work",
                "sections": _sections(path),
            },
        }
    return records


def write_records(records: dict[str, dict], *, repo_root: Path = ROOT) -> None:
    output_dir = repo_root / "data" / "structured-text"
    source_dir = repo_root / "sources" / "structured-text"
    output_paths = {resource_id: output_dir / f"{resource_id}.json" for resource_id in sorted(records)}
    previous = {resource_id: load_json(path) for resource_id, path in output_paths.items()}
    with writer_manifest.run(
        writer_identity=WRITER_IDENTITY,
        writer_version=SCRIPT_VERSION,
        data_paths=list(output_paths.values()),
        repo_root=repo_root,
        manifests_dir=repo_root / "review" / "writer-manifests",
    ) as manifest_run:
        for resource_id, path in output_paths.items():
            record = records[resource_id]
            write_json(path, record)
            entries_changed, fields_changed = envelope_delta_counts(previous[resource_id], record)
            manifest_run.record_delta(path, entries_changed=entries_changed, fields_changed=fields_changed)
            meta = record["meta"]
            write_json(
                source_dir / resource_id / "config.json",
                {
                    "resource_id": resource_id,
                    "title": meta["title"],
                    "author": meta["author"],
                    "contributors": meta["contributors"],
                    "original_publication_year": meta["original_publication_year"],
                    "language": meta["language"],
                    "original_language": meta["original_language"],
                    "tradition": meta["tradition"],
                    "raw_filename": SPEC_DEFAULTS[resource_id]["raw_filename"],
                    "license": meta["license"],
                    "schema_type": meta["schema_type"],
                    **meta["provenance"],
                },
            )


def main() -> int:
    cli=argparse.ArgumentParser(); cli.add_argument("--write", action="store_true"); args=cli.parse_args()
    records=build_records()
    if args.write: write_records(records)
    print(f"Parsed {len(records)} public-domain works")
    return 0

if __name__ == "__main__": raise SystemExit(main())
