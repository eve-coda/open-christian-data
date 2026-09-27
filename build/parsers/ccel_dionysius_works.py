"""Parse both public-domain Parker volumes of Pseudo-Dionysius from CCEL ThML."""
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

RAW = ROOT / "raw" / "ccel" / "dionysius-works.xml"
OUT = ROOT / "data" / "structured-text" / "pseudo-dionysius-works-parker.json"
SOURCE = ROOT / "sources" / "structured-text" / "pseudo-dionysius-works-parker" / "config.json"
PROVENANCE_DATE = "2026-09-17"
WRITER_IDENTITY = "ccel_dionysius_works_parser"
SCRIPT_VERSION = "build/parsers/ccel_dionysius_works.py@v1.0.0"


def build_record() -> dict:
    raw = RAW.read_bytes()
    root = ET.fromstring(preprocess_thml(raw))
    body = root.find("ThML.body")
    if body is None:
        raise RuntimeError(f"missing ThML.body in {RAW}")
    sections = []
    for div in body:
        title = clean_text(div.get("title", ""))
        if not div.tag.startswith("div") or title == "Indexes":
            continue
        section = parse_div(div, 0)
        if section:
            sections.append(section)
    if {section.get("title") for section in sections} != {"Volume 1", "Volume 2"}:
        raise RuntimeError("expected both Parker volumes in CCEL source")
    return {
        "meta": {
            "id": "pseudo-dionysius-works-parker",
            "title": "The Works of Dionysius the Areopagite, Volumes I–II",
            "author": "Pseudo-Dionysius the Areopagite",
            "author_birth_year": None,
            "author_death_year": None,
            "contributors": [
                {"name": "John Parker", "role": "translator"},
                {"name": "Christian Classics Ethereal Library", "role": "transcriber"},
            ],
            "original_publication_year": 500,
            "language": "en",
            "original_language": "grc",
            "tradition": ["patristic", "monastic"],
            "tradition_notes": "The complete surviving Pseudo-Dionysian corpus in Parker's two-volume English translation.",
            "era": "patristic",
            "audience": "scholarly",
            "license": "public-domain",
            "schema_type": "structured_text",
            "schema_version": "2.1.0",
            "completeness": "full",
            "provenance": {
                "source_url": "https://www.ccel.org/ccel/dionysius/works.xml",
                "source_format": "ThML XML",
                "source_edition": "John Parker, trans., The Works of Dionysius the Areopagite, Vol. I (1897) and Vol. II (1899)",
                "download_date": PROVENANCE_DATE,
                "source_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "processing_method": "automated",
                "processing_script_version": SCRIPT_VERSION,
                "processing_date": PROVENANCE_DATE,
                "notes": "Both Parker volumes retained; generated indexes excluded.",
            },
        },
        "data": {
            "work_id": "pseudo-dionysius-works-parker",
            "work_kind": "theological-work",
            "sections": sections,
        },
    }


def write_record(record: dict, *, repo_root: Path = ROOT) -> None:
    output = repo_root / "data" / "structured-text" / "pseudo-dionysius-works-parker.json"
    source = repo_root / "sources" / "structured-text" / "pseudo-dionysius-works-parker" / "config.json"
    previous = load_json(output)
    meta = record["meta"]
    with writer_manifest.run(
        writer_identity=WRITER_IDENTITY,
        writer_version=SCRIPT_VERSION,
        data_paths=[output],
        repo_root=repo_root,
        manifests_dir=repo_root / "review" / "writer-manifests",
    ) as manifest_run:
        write_json(output, record)
        entries_changed, fields_changed = envelope_delta_counts(previous, record)
        manifest_run.record_delta(output, entries_changed=entries_changed, fields_changed=fields_changed)
        write_json(
            source,
            {
                "resource_id": meta["id"],
                "title": meta["title"],
                "author": meta["author"],
                "license": meta["license"],
                "schema_type": meta["schema_type"],
                **meta["provenance"],
            },
        )


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--write", action="store_true")
    args = cli.parse_args()
    record = build_record()
    if args.write:
        write_record(record)
    print("Parsed both Parker Pseudo-Dionysius volumes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
