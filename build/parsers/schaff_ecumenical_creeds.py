"""Extract three historically distinct Nicene creed forms from Schaff.

The existing ``nicene-creed.json`` conflated the 381 creed with the later
Western filioque form.  This parser keeps the stable resource id for the 381
form, adds the original 325 creed, and records the Western received form as a
separate document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from build.lib.contributors import normalize_contributors  # noqa: E402
from build.lib import writer_manifest  # noqa: E402
from build.lib.corpus_writer import (  # noqa: E402
    envelope_delta_counts,
    load_json,
    manifest_delta_counts,
    write_json,
)
from build.parsers.ccel_schaff_hcc import (  # noqa: E402
    clean_text,
    get_all_text,
    preprocess_thml,
)

RAW_1 = REPO_ROOT / "raw" / "ccel" / "schaff" / "creeds1.xml"
RAW_2 = REPO_ROOT / "raw" / "ccel" / "schaff" / "creeds2.xml"
OUTPUT_DIR = REPO_ROOT / "data" / "doctrinal-documents"
SOURCE_DIR = REPO_ROOT / "sources" / "doctrinal-documents"
SCHEMA_VERSION = "2.1.0"
SCRIPT_VERSION = "build/parsers/schaff_ecumenical_creeds.py@v1.0.0"
PROVENANCE_DATE = "2026-09-17"
WRITER_IDENTITY = "schaff_ecumenical_creeds_parser"


def _normalise(parts: list[str]) -> str:
    text = " ".join(part.strip() for part in parts if part.strip())
    return re.sub(r"\s+", " ", text).strip()


def _find_div(root: ET.Element, title: str) -> ET.Element:
    for element in root.findall(".//*"):
        if element.tag.startswith("div") and clean_text(element.get("title", "")) == title:
            return element
    raise RuntimeError(f"Schaff division not found: {title}")


def _comparative_english_creeds(root: ET.Element) -> tuple[str, str]:
    section = _find_div(root, "The Nicene Creed.")
    tables = section.findall(".//table")
    start = next(
        index
        for index, table in enumerate(tables)
        if "The Nicene Creed of 325" in clean_text(get_all_text(table))
    )
    parts = [[], []]
    for table_index, table in enumerate(tables[start : start + 2]):
        for row_index, row in enumerate(table.findall("tr")):
            cells = row.findall("td")
            if len(cells) != 2:
                continue
            if table_index == 0 and row_index == 0:
                continue
            for column, cell in enumerate(cells):
                text = clean_text(get_all_text(cell))
                if text:
                    parts[column].append(text)
    return _normalise(parts[0]), _normalise(parts[1])


def _western_received_creed(root: ET.Element) -> str:
    section = _find_div(root, "Forma Recepta, Ecclesiæ Occidentalis.")
    parts: list[str] = []
    for table_index, table in enumerate(child for child in section if child.tag == "table"):
        for row_index, row in enumerate(table.findall("tr")):
            cells = row.findall("td")
            if len(cells) != 2:
                continue
            if table_index == 0 and row_index == 0:
                continue
            text = clean_text(get_all_text(cells[1]))
            if text:
                parts.append(text)
    return _normalise(parts)


def _record(
    *,
    resource_id: str,
    title: str,
    author: str,
    year: int,
    text: str,
    source_url: str,
    source_hash: str,
    tradition_notes: str,
    source_edition: str | None = None,
    source_notes: str | None = None,
) -> dict:
    return {
        "meta": {
            "id": resource_id,
            "title": title,
            "author": author,
            "author_birth_year": None,
            "author_death_year": None,
            "contributors": normalize_contributors(
                [
                    "Philip Schaff (editor)",
                    "Christian Classics Ethereal Library (digital edition)",
                ]
            ),
            "original_publication_year": year,
            "language": "en",
            "tradition": ["ecumenical", "patristic"],
            "tradition_notes": tradition_notes,
            "license": "public-domain",
            "schema_type": "doctrinal_document",
            "schema_version": SCHEMA_VERSION,
            "completeness": "full",
            "provenance": {
                "source_url": source_url,
                "source_format": "ThML XML",
                "source_edition": source_edition
                or (
                    "Philip Schaff, The Creeds of Christendom, sixth edition, "
                    "revised and enlarged by David S. Schaff; CCEL ThML transcription"
                ),
                "download_date": PROVENANCE_DATE,
                "source_hash": source_hash,
                "processing_method": "automated",
                "processing_script_version": SCRIPT_VERSION,
                "processing_date": PROVENANCE_DATE,
                "notes": source_notes
                or (
                    "English text extracted from Schaff's parallel presentation. "
                    "This record deliberately distinguishes the 325, 381, and later "
                    "Western forms."
                ),
            },
        },
        "data": {
            "document_id": resource_id,
            "document_kind": "creed",
            "revision_history": [],
            "units": [{"unit_type": "text", "content": text}],
        },
    }


def extract_records() -> dict[str, dict]:
    if not RAW_1.exists() or not RAW_2.exists():
        raise FileNotFoundError("Schaff creeds1.xml and creeds2.xml are required")
    raw_1 = RAW_1.read_bytes()
    raw_2 = RAW_2.read_bytes()
    root_1 = ET.fromstring(preprocess_thml(raw_1))
    root_2 = ET.fromstring(preprocess_thml(raw_2))
    creed_325, creed_381 = _comparative_english_creeds(root_1)
    western = _western_received_creed(root_2)
    hash_1 = "sha256:" + hashlib.sha256(raw_1).hexdigest()
    hash_2 = "sha256:" + hashlib.sha256(raw_2).hexdigest()

    return {
        "nicene-creed-325": _record(
            resource_id="nicene-creed-325",
            title="Nicene Creed (325)",
            author="First Council of Nicaea",
            year=325,
            text=creed_325,
            source_url="https://www.ccel.org/ccel/schaff/creeds1.xml",
            source_hash=hash_1,
            tradition_notes=(
                "The original creed adopted at Nicaea in 325, including its concluding "
                "anathemas; distinct from the expanded creed associated with 381."
            ),
        ),
        "nicene-creed": _record(
            resource_id="nicene-creed",
            title="Niceno-Constantinopolitan Creed (381)",
            author="First Council of Constantinople",
            year=381,
            text=creed_381,
            source_url="https://www.ccel.org/ccel/schaff/creeds1.xml",
            source_hash=hash_1,
            tradition_notes=(
                "The Constantinopolitan form received as the creed of 381. The text "
                "confesses that the Holy Spirit proceeds from the Father and does not "
                "contain the later Western filioque addition."
            ),
        ),
        "nicene-creed-anglican-bcp-1662": _record(
            resource_id="nicene-creed-anglican-bcp-1662",
            title=(
                "Niceno-Constantinopolitan Creed: Anglican Book of Common Prayer "
                "(1662), Schaff Protestant Received Text"
            ),
            author="Church of England",
            year=1662,
            text=western,
            source_url="https://www.ccel.org/ccel/schaff/creeds2.xml",
            source_hash=hash_2,
            tradition_notes=(
                "Schaff's English Protestant received-text column, taken from the Anglican "
                "Book of Common Prayer (1662), containing the Western filioque and other "
                "bracketed Western additions; not the creed promulgated in 381."
            ),
            source_edition=(
                "Anglican Book of Common Prayer (1662), Nicene Creed; Protestant "
                "received-text column in Philip Schaff, The Creeds of Christendom, "
                "sixth edition, revised and enlarged by David S. Schaff; CCEL ThML "
                "transcription"
            ),
            source_notes=(
                "Protestant received-text column from the Anglican Book of Common Prayer "
                "(1662), as printed by Schaff. Schaff states that Western additions are "
                "enclosed in brackets; those editorial brackets are preserved exactly, "
                "including [God of God], [essence], [I believe], and [and the Son]."
            ),
        ),
    }


def _build_collection_manifest(data_dir: Path, previous: dict | None) -> dict:
    entries = []
    for path in sorted(data_dir.glob("*.json")):
        if path.name == "_manifest.json":
            continue
        payload = load_json(path)
        if not payload or not isinstance(payload.get("meta"), dict) or not isinstance(payload.get("data"), dict):
            continue
        entries.append(
            {
                "id": payload["meta"]["id"],
                "title": payload["meta"]["title"],
                "document_kind": payload["data"]["document_kind"],
                "file": path.name,
            }
        )
    previous_date = str((previous or {}).get("last_updated") or PROVENANCE_DATE)
    return {
        "schema_type": "doctrinal_document",
        "schema_version": "2.1.0",
        "documents": sorted(entries, key=lambda entry: entry["id"]),
        "stats": {"total_documents": len(entries)},
        "last_updated": max(previous_date, PROVENANCE_DATE),
    }


def write_records(records: dict[str, dict], *, repo_root: Path = REPO_ROOT) -> None:
    output_dir = repo_root / "data" / "doctrinal-documents"
    source_dir = repo_root / "sources" / "doctrinal-documents"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {resource_id: output_dir / f"{resource_id}.json" for resource_id in sorted(records)}
    manifest_path = output_dir / "_manifest.json"
    previous_records = {resource_id: load_json(path) for resource_id, path in output_paths.items()}
    previous_manifest = load_json(manifest_path)
    with writer_manifest.run(
        writer_identity=WRITER_IDENTITY,
        writer_version=SCRIPT_VERSION,
        data_paths=[*output_paths.values(), manifest_path],
        allowed_field_paths=("/meta", "/data", "/documents", "/stats", "/last_updated"),
        repo_root=repo_root,
        manifests_dir=repo_root / "review" / "writer-manifests",
    ) as manifest_run:
        for resource_id, output in output_paths.items():
            record = records[resource_id]
            write_json(output, record)
            entries_changed, fields_changed = envelope_delta_counts(previous_records[resource_id], record)
            manifest_run.record_delta(output, entries_changed=entries_changed, fields_changed=fields_changed)
            meta = record["meta"]
            write_json(
                source_dir / resource_id / "config.json",
                {
                    "resource_id": resource_id,
                    "title": meta["title"],
                    "author": meta["author"],
                    "original_publication_year": meta["original_publication_year"],
                    "license": meta["license"],
                    "schema_type": meta["schema_type"],
                    **meta["provenance"],
                },
            )
        manifest = _build_collection_manifest(output_dir, previous_manifest)
        write_json(manifest_path, manifest)
        entries_changed, fields_changed = manifest_delta_counts(previous_manifest, manifest)
        manifest_run.record_delta(manifest_path, entries_changed=entries_changed, fields_changed=fields_changed)


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--write", action="store_true")
    args = cli.parse_args(argv)
    records = extract_records()
    if args.write:
        write_records(records)
    print(f"Extracted {len(records)} historically distinct creed forms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
