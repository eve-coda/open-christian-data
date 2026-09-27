"""Parse Project Wittenberg's public-domain Concordia Triglotta texts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from build.lib import writer_manifest
from build.lib.corpus_writer import envelope_delta_counts, load_json, write_json

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "project-wittenberg" / "boc"
OUT = ROOT / "data" / "structured-text"
SOURCES = ROOT / "sources" / "structured-text"
PROVENANCE_DATE = "2026-09-17"
WRITER_IDENTITY = "project_wittenberg_boc_parser"
SCRIPT_VERSION = "build/parsers/project_wittenberg_boc.py@v1.0.1"
PROJECT_WITTENBERG_NOTICE = (
    "This text was converted to ascii format for Project Wittenberg by Allen "
    "Mulvey and is in the public domain. You may freely distribute, copy or "
    "print this text. Please direct any comments or suggestions to: Rev. Robert "
    "E. Smith of the Walther Library at Concordia Theological Seminary."
)
CANONICAL_FOOTER_PATTERNS = (
    r"this\s+text\s+was\s+converted\s+to\s+ascii\s+format\s+for\s+project\s+wittenberg",
    r"by\s+allen\s+mulvey\s+and\s+is\s+in\s+the\s+public\s+domain",
    r"you\s+may\s+freely\s+distribute,\s+copy\s+or\s+print\s+this\s+text",
)
CONTACT_FOOTER_PATTERNS = (
    r"(?:com)?ments\s+or\s+suggestions\s+to\s*:",
    r"\brev\.\s+robert\s+e\.\s+smith\b",
    r"\b(?:of\s+the\s+)?walther\s+library\b",
    r"(?m)^[ \t]*surface\s+mail\s*:",
    r"(?m)^[ \t]*e-?mail\s*:",
    r"(?m)^[ \t]*(?:usa\s+)?phone\s*:",
    r"(?m)^[ \t]*fax\s*:",
)

SPECS = {
    "apology-augsburg-confession": {
        "title": "Apology of the Augsburg Confession",
        "author": "Philipp Melanchthon",
        "year": 1531,
        "original_language": "la",
        "files": sorted((RAW / "ap").glob("*.asc")),
        "url": "https://www.projectwittenberg.org/etext/boc/ap/",
    },
    "smalcald-articles": {
        "title": "The Smalcald Articles",
        "author": "Martin Luther",
        "year": 1537,
        "original_language": "de",
        "files": sorted((RAW / "sa").glob("*.asc")),
        "url": "https://www.projectwittenberg.org/etext/boc/sa/",
    },
    "power-primacy-pope": {
        "title": "Treatise on the Power and Primacy of the Pope",
        "author": "Philipp Melanchthon",
        "year": 1537,
        "original_language": "la",
        "files": [RAW / "primacy.asc"],
        "url": "https://www.projectwittenberg.org/etext/boc/tr/primacy.asc",
    },
}


def _is_forbidden_text_character(character: str) -> bool:
    return character == "\ufffd" or (
        character not in "\n\t" and unicodedata.category(character) == "Cc"
    )


def _remove_embedded_corrupt_footer(text: str) -> str:
    """Remove a contact block injected before a control-character run, keeping later text."""
    markers = sorted(
        (
            match
            for pattern in CONTACT_FOOTER_PATTERNS
            if (match := re.search(pattern, text, flags=re.IGNORECASE))
        ),
        key=lambda match: match.start(),
    )
    for marker in markers:
        control_start = next(
            (
                index
                for index in range(marker.end(), len(text))
                if _is_forbidden_text_character(text[index])
            ),
            None,
        )
        if control_start is None:
            continue
        control_end = control_start
        while control_end < len(text) and _is_forbidden_text_character(text[control_end]):
            control_end += 1
        if text[control_end:].strip():
            return text[: marker.start()] + text[control_end:]
    return text


def _paragraphs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    text = _remove_embedded_corrupt_footer(text)
    text = "".join(
        character for character in text if not _is_forbidden_text_character(character)
    )
    markers = [
        match
        for pattern in (*CANONICAL_FOOTER_PATTERNS, *CONTACT_FOOTER_PATTERNS)
        if (match := re.search(pattern, text, flags=re.IGNORECASE))
    ]
    if markers:
        marker = min(markers, key=lambda match: match.start())
        text = re.sub(r"[\x00\s_]+$", "", text[: marker.start()])
    blocks = []
    for raw in re.split(r"\n\s*\n", text):
        block = re.sub(r"\s+", " ", raw.replace("_", "")).strip()
        if block:
            blocks.append(block)
    return blocks


def _hash(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def build_records() -> dict[str, dict]:
    records = {}
    for resource_id, spec in SPECS.items():
        files = spec["files"]
        if not files or any(not path.exists() for path in files):
            raise FileNotFoundError(f"missing Project Wittenberg files for {resource_id}")
        sections = []
        for index, path in enumerate(files, start=1):
            blocks = _paragraphs(path)
            sections.append(
                {
                    "section_type": "section",
                    "label": f"Part {index}",
                    "title": blocks[0][:160],
                    "content_blocks": blocks,
                    "scripture_references": [],
                    "word_count": sum(len(block.split()) for block in blocks),
                    "children": [],
                }
            )
        records[resource_id] = {
            "meta": {
                "id": resource_id,
                "title": spec["title"],
                "author": spec["author"],
                "author_birth_year": None,
                "author_death_year": None,
                "contributors": [
                    {"name": "F. Bente", "role": "translator"},
                    {"name": "W. H. T. Dau", "role": "translator"},
                    {"name": "Project Wittenberg", "role": "transcriber"},
                ],
                "original_publication_year": spec["year"],
                "language": "en",
                "original_language": spec["original_language"],
                "tradition": ["lutheran", "confessional"],
                "tradition_notes": "A constituent document of the Lutheran Book of Concord.",
                "era": "reformation",
                "audience": "scholarly",
                "license": "public-domain",
                "schema_type": "structured_text",
                "schema_version": "2.1.0",
                "completeness": "full",
                "provenance": {
                    "source_url": spec["url"],
                    "source_format": "plain text",
                    "source_edition": (
                        "Concordia Triglotta: The Symbolical Books of the Evangelical "
                        "Lutheran Church, St. Louis: Concordia Publishing House, 1921; "
                        "F. Bente and W. H. T. Dau translation"
                    ),
                    "download_date": PROVENANCE_DATE,
                    "source_hash": _hash(files),
                    "processing_method": "automated",
                    "processing_script_version": SCRIPT_VERSION,
                    "processing_date": PROVENANCE_DATE,
                    "notes": (
                        "Project Wittenberg ASCII parts preserved as ordered sections; "
                        "repeated distribution/contact boilerplate removed from searchable "
                        f"content. {PROJECT_WITTENBERG_NOTICE}"
                    ),
                },
            },
            "data": {
                "work_id": resource_id,
                "work_kind": "theological-work",
                "sections": sections,
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
                    "license": meta["license"],
                    "schema_type": meta["schema_type"],
                    **meta["provenance"],
                },
            )


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--write", action="store_true")
    args = cli.parse_args()
    records = build_records()
    if args.write:
        write_records(records)
    print(f"Parsed {len(records)} Book of Concord documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
