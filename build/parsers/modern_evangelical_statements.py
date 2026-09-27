"""Parse modern evangelical doctrinal statements from cached official HTML."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from jsonschema import Draft202012Validator

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from build.lib import writer_manifest  # noqa: E402
from build.lib.paths import REPO_ROOT  # noqa: E402


_WHITESPACE_RE = re.compile(r"\s+")
_EFCA_HEADING_RE = re.compile(r"^Article\s+(\d+)\.\s*(.+)$")
SCRIPT_VERSION = "build/parsers/modern_evangelical_statements.py@v1.0.0"
WRITER_IDENTITY = "modern_evangelical_statements_parser"
CONFIG_ROOT = REPO_ROOT / "sources" / "doctrinal-documents"
SCHEMA_PATH = REPO_ROOT / "schemas" / "v1" / "doctrinal_document.schema.json"
DOCUMENT_IDS = (
    "efca-statement-of-faith-2019",
    "nae-statement-of-faith-current",
    "lausanne-seoul-statement-2024-sacraments-summary",
)


def _text(node: Tag) -> str:
    """Return visible node text with deterministic whitespace."""
    return _WHITESPACE_RE.sub(" ", node.get_text(" ", strip=True)).strip()


def extract_efca_statement(html_bytes: bytes) -> list[dict]:
    """Extract the ten articles from the official EFCA Statement of Faith page."""
    soup = BeautifulSoup(html_bytes, "html.parser")
    article_list = soup.select_one("ol.articles")
    if article_list is None:
        raise ValueError("EFCA source is missing ol.articles")

    units: list[dict] = []
    for item in article_list.find_all("li", recursive=False):
        heading = item.find(["h2", "h3"])
        if heading is None:
            raise ValueError("EFCA article is missing its heading")
        match = _EFCA_HEADING_RE.fullmatch(_text(heading))
        if match is None:
            raise ValueError(f"Unexpected EFCA article heading: {_text(heading)!r}")
        paragraphs = [_text(p) for p in item.find_all("p") if _text(p)]
        if not paragraphs:
            raise ValueError(f"EFCA Article {match.group(1)} has no content")
        units.append(
            {
                "unit_type": "article",
                "number": match.group(1),
                "title": match.group(2),
                "content": "\n\n".join(paragraphs),
            }
        )

    expected = [str(number) for number in range(1, 11)]
    actual = [unit["number"] for unit in units]
    if actual != expected:
        raise ValueError(f"Expected EFCA articles {expected}, got {actual}")
    return units


def extract_nae_statement(html_bytes: bytes) -> list[dict]:
    """Extract the seven paragraphs from the official NAE Statement of Faith page."""
    soup = BeautifulSoup(html_bytes, "html.parser")
    page = soup.select_one("#page-builder-container")
    if page is None:
        raise ValueError("NAE source is missing #page-builder-container")
    rows = page.select("div.content-row.content-type.container")
    if not rows:
        raise ValueError("NAE source has no statement content row")

    paragraphs = [
        _text(paragraph)
        for paragraph in rows[0].find_all("p")
        if _text(paragraph).startswith("We believe")
    ]
    if len(paragraphs) != 7:
        raise ValueError(f"Expected 7 NAE belief paragraphs, got {len(paragraphs)}")
    return [
        {
            "unit_type": "article",
            "number": str(index),
            "title": f"Article {index}",
            "content": content,
        }
        for index, content in enumerate(paragraphs, 1)
    ]


def build_lausanne_sacraments_summary(html_bytes: bytes) -> list[dict]:
    """Build an original research summary without republishing Lausanne's full text."""
    soup = BeautifulSoup(html_bytes, "html.parser")
    content = soup.select_one("div.lop-the-content")
    if content is None:
        raise ValueError("Lausanne source is missing div.lop-the-content")
    source_text = _text(content).lower()
    required_anchors = (
        "christian baptism is a sign and seal",
        "see, feel and taste his grace",
        "regular rehearsing of the gospel",
    )
    missing = [anchor for anchor in required_anchors if anchor not in source_text]
    if missing:
        raise ValueError(f"Lausanne source is missing expected sacramental anchors: {missing}")

    return [
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


def build_document(config: dict, units: list[dict]) -> dict:
    """Build one schema-valid doctrinal-document envelope from source config."""
    source = config["source"]
    processing = config["processing"]
    data = {
        "document_id": config["id"],
        "document_kind": "declaration",
        "units": units,
    }
    if "revision_history" in config:
        data["revision_history"] = config["revision_history"]
    return {
        "meta": {
            "id": config["id"],
            "title": config["title"],
            "author": config["author"],
            "original_publication_year": config["original_publication_year"],
            "language": "en",
            "tradition": config["tradition"],
            "tradition_notes": config["tradition_notes"],
            "license": config["license"],
            "schema_type": "doctrinal_document",
            "schema_version": "2.1.0",
            "completeness": config["completeness"],
            "provenance": {
                "source_url": source["url"],
                "source_format": source["format"],
                "source_edition": source["edition"],
                "download_date": source["download_date"],
                "source_hash": source["source_hash"],
                "processing_method": processing["method"],
                "processing_script_version": SCRIPT_VERSION,
                "processing_date": processing["date"],
                "notes": processing["notes"],
            },
        },
        "data": data,
    }


def load_document_configs() -> dict[str, dict]:
    """Load and minimally validate all source configs."""
    configs: dict[str, dict] = {}
    for document_id in DOCUMENT_IDS:
        config_path = CONFIG_ROOT / document_id / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config.get("id") != document_id:
            raise ValueError(f"Config ID mismatch in {config_path}: {config.get('id')!r}")
        if config.get("output_file") != f"data/doctrinal-documents/{document_id}.json":
            raise ValueError(f"Output path mismatch for {document_id}")
        configs[document_id] = config
    return configs


def _verified_raw_bytes(config: dict) -> bytes:
    raw_path = REPO_ROOT / config["raw_file"]
    if not raw_path.exists():
        raise FileNotFoundError(f"Missing cached raw witness: {raw_path.relative_to(REPO_ROOT)}")
    raw_bytes = raw_path.read_bytes()
    actual_hash = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    expected_hash = config["source"]["source_hash"]
    if actual_hash != expected_hash:
        raise ValueError(
            f"Raw witness hash mismatch for {config['id']}: "
            f"expected {expected_hash}, got {actual_hash}"
        )
    return raw_bytes


def parse_document(config: dict) -> dict:
    """Parse one verified cached witness into a doctrinal-document record."""
    raw_bytes = _verified_raw_bytes(config)
    extractors = {
        "efca-statement-of-faith-2019": extract_efca_statement,
        "nae-statement-of-faith-current": extract_nae_statement,
        "lausanne-seoul-statement-2024-sacraments-summary": (
            build_lausanne_sacraments_summary
        ),
    }
    try:
        extractor = extractors[config["id"]]
    except KeyError as exc:
        raise ValueError(f"No extractor registered for {config['id']}") from exc
    return build_document(config, extractor(raw_bytes))


def build_synced_manifest(
    existing_manifest: dict,
    *,
    data_dir: Path,
    generated_documents: dict[str, dict],
    update_date: str,
) -> dict:
    """Return a doctrinal manifest synchronized to real and pending JSON records."""
    documents: dict[str, dict] = {}
    for path in sorted(data_dir.glob("*.json")):
        if path.name == "_manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        document_id = payload["meta"]["id"]
        if path.stem != document_id:
            raise ValueError(f"Document ID/file mismatch: {path.name} != {document_id}")
        documents[document_id] = payload
    documents.update(generated_documents)

    entries = [
        {
            "id": document_id,
            "title": payload["meta"]["title"],
            "document_kind": payload["data"]["document_kind"],
            "file": f"{document_id}.json",
        }
        for document_id, payload in sorted(documents.items())
    ]
    return {
        "schema_type": existing_manifest.get("schema_type", "doctrinal_document"),
        "schema_version": existing_manifest.get("schema_version", "2.1.0"),
        "documents": entries,
        "stats": {"total_documents": len(entries)},
        "last_updated": max(existing_manifest.get("last_updated", update_date), update_date),
    }


def validate_documents(documents: dict[str, dict]) -> None:
    """Validate every generated record against the doctrinal-document schema."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for document_id in sorted(documents):
        validator.validate(documents[document_id])


def write_generated_documents(
    documents: dict[str, dict],
    *,
    repo_root: Path = REPO_ROOT,
    update_date: str,
    dry_run: bool,
) -> None:
    """Validate and write generated records and a synchronized manifest."""
    validate_documents(documents)
    if dry_run:
        return

    data_dir = repo_root / "data" / "doctrinal-documents"
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = data_dir / "_manifest.json"
    if manifest_path.exists():
        previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        previous_manifest = {
            "schema_type": "doctrinal_document",
            "schema_version": "2.1.0",
            "documents": [],
            "stats": {"total_documents": 0},
            "last_updated": update_date,
        }
    synced_manifest = build_synced_manifest(
        previous_manifest,
        data_dir=data_dir,
        generated_documents=documents,
        update_date=update_date,
    )

    output_paths = {
        document_id: data_dir / f"{document_id}.json"
        for document_id in sorted(documents)
    }
    previous_documents = {
        document_id: (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        )
        for document_id, path in output_paths.items()
    }
    data_paths = [*output_paths.values(), manifest_path]

    with writer_manifest.run(
        writer_identity=WRITER_IDENTITY,
        writer_version=SCRIPT_VERSION,
        data_paths=data_paths,
        repo_root=repo_root,
        manifests_dir=repo_root / "review" / "writer-manifests",
    ) as manifest_run:
        for document_id, path in output_paths.items():
            _write_json(path, documents[document_id])
            entries_changed, fields_changed = _document_delta_counts(
                previous_documents[document_id], documents[document_id]
            )
            manifest_run.record_delta(
                path,
                entries_changed=entries_changed,
                fields_changed=fields_changed,
            )
        _write_json(manifest_path, synced_manifest)
        entries_changed, fields_changed = _manifest_delta_counts(
            previous_manifest, synced_manifest
        )
        manifest_run.record_delta(
            manifest_path,
            entries_changed=entries_changed,
            fields_changed=fields_changed,
        )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _document_delta_payload(document: dict | None) -> dict | None:
    if document is None:
        return None
    meta = document["meta"]
    data = document["data"]
    entries = [meta, {key: value for key, value in data.items() if key != "units"}]
    entries.extend(data.get("units", []))
    return {"meta": {}, "data": entries}


def _document_delta_key(entry: dict) -> str:
    if "document_id" in entry:
        return f"data:{entry['document_id']}"
    if "unit_type" in entry:
        return f"unit:{entry['unit_type']}:{entry.get('number', '')}"
    return f"meta:{entry['id']}"


def _document_delta_counts(before: dict | None, after: dict) -> tuple[int, int]:
    return writer_manifest.diff_counts(
        _document_delta_payload(before),
        _document_delta_payload(after) or {},
        key=_document_delta_key,
    )


def _manifest_delta_counts(before: dict, after: dict) -> tuple[int, int]:
    before_payload = {"meta": {}, "data": before.get("documents", [])}
    after_payload = {"meta": {}, "data": after.get("documents", [])}
    return writer_manifest.diff_counts(
        before_payload,
        after_payload,
        key=lambda entry: entry["id"],
    )


def main(argv: list[str] | None = None) -> int:
    argument_parser = argparse.ArgumentParser(
        description="Parse modern evangelical statements from cached official HTML."
    )
    selection = argument_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="parse all configured records")
    selection.add_argument("--document", choices=DOCUMENT_IDS, help="parse one record")
    argument_parser.add_argument(
        "--dry-run", action="store_true", help="parse and validate without writing"
    )
    args = argument_parser.parse_args(argv)

    configs = load_document_configs()
    selected_ids = DOCUMENT_IDS if args.all else (args.document,)
    selected = {document_id: parse_document(configs[document_id]) for document_id in selected_ids}
    update_date = max(configs[document_id]["processing"]["date"] for document_id in selected_ids)
    write_generated_documents(
        selected,
        repo_root=REPO_ROOT,
        update_date=update_date,
        dry_run=args.dry_run,
    )
    mode = "validated" if args.dry_run else "written"
    print(f"{mode}: {len(selected)} document(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
