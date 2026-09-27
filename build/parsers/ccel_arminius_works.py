"""Parse the public-domain Nichols/Bagnall Works of James Arminius."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build.parsers.ccel_creeds_of_christendom import parse_div
from build.parsers.ccel_schaff_hcc import clean_text, preprocess_thml
from build.lib import writer_manifest
from build.lib.corpus_writer import envelope_delta_counts, load_json, write_json

RAW = ROOT / "raw" / "ccel" / "arminius"
OUT = ROOT / "data" / "structured-text"
SOURCES = ROOT / "sources" / "structured-text"
PROVENANCE_DATE = "2026-09-17"
WRITER_IDENTITY = "ccel_arminius_works_parser"
SCRIPT_VERSION = "build/parsers/ccel_arminius_works.py@v1.0.0"


def build_records() -> dict[str, dict]:
    records = {}
    for volume in (1, 2, 3):
        path = RAW / f"works{volume}.xml"
        raw = path.read_bytes()
        root = ET.fromstring(preprocess_thml(raw))
        body = root.find("ThML.body")
        if body is None:
            raise RuntimeError(f"missing ThML.body in {path}")
        sections = []
        for div in body:
            title = clean_text(div.get("title", ""))
            if not div.tag.startswith("div") or title == "Indexes":
                continue
            section = parse_div(div, 0)
            if section:
                sections.append(section)
        resource_id = f"arminius-works-vol-{volume}"
        records[resource_id] = {
            "meta": {
                "id": resource_id,
                "title": f"The Works of James Arminius, Vol. {volume}",
                "author": "Jacobus Arminius",
                "author_birth_year": 1560,
                "author_death_year": 1609,
                "contributors": [
                    {"name": "James Nichols", "role": "translator"},
                    {"name": "William R. Bagnall", "role": "translator"},
                    {"name": "Christian Classics Ethereal Library", "role": "transcriber"},
                ],
                "original_publication_year": 1629,
                "language": "en",
                "original_language": "la",
                "tradition": ["arminian", "reformed"],
                "tradition_notes": "Primary writings of Jacobus Arminius, including his Declaration of Sentiments.",
                "era": "post-reformation",
                "audience": "scholarly",
                "license": "public-domain",
                "schema_type": "structured_text",
                "schema_version": "2.1.0",
                "completeness": "full",
                "provenance": {
                    "source_url": f"https://www.ccel.org/ccel/arminius/works{volume}.xml",
                    "source_format": "ThML XML",
                    "source_edition": (
                        "The Works of James Arminius, translated by James Nichols and "
                        "William R. Bagnall, three-volume English edition, 1853"
                    ),
                    "download_date": PROVENANCE_DATE,
                    "source_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "processing_method": "automated",
                    "processing_script_version": SCRIPT_VERSION,
                    "processing_date": PROVENANCE_DATE,
                    "notes": "Front matter retained; generated indexes excluded.",
                },
            },
            "data": {"work_id": resource_id, "work_kind": "theological-work", "sections": sections},
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
                {"resource_id": resource_id, "title": meta["title"], "author": meta["author"], "license": meta["license"], "schema_type": meta["schema_type"], **meta["provenance"]},
            )


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--write", action="store_true")
    args = cli.parse_args()
    records = build_records()
    if args.write:
        write_records(records)
    print(f"Parsed {len(records)} Arminius volumes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
