"""Parser for Philip Schaff's three-volume *Creeds of Christendom* (CCEL
ThML), into one OCD ``structured_text`` JSON file per volume.

Schaff's Vol. I is a prose history of the creeds organised as div1 (chapter) >
div2 (section) > div3 (subsection). This parser recurses all three levels into
the structured_text section tree, skipping front/back matter (Title Page,
Prefatory, Indexes) and footnotes (<note>, excluded by get_all_text).

ThML preprocessing, text extraction, and scripture-ref helpers are reused from
ccel_schaff_hcc (same author, same CCEL ThML conventions) to keep behaviour
consistent across the two Schaff parsers.

Usage:
    py -3 build/parsers/ccel_creeds_of_christendom.py --volume all --dry-run
    py -3 build/parsers/ccel_creeds_of_christendom.py --volume all --parse
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from build.lib.contributors import normalize_contributors  # noqa: E402
from build.lib import writer_manifest  # noqa: E402
from build.lib.corpus_writer import envelope_delta_counts, load_json, write_json  # noqa: E402
from build.lib.paths import REPO_ROOT  # noqa: E402
# Reuse the stable ThML machinery from the sibling Schaff parser.
from build.parsers.ccel_schaff_hcc import (  # noqa: E402
    _DIV_TAG_RE,
    _HEADING_TAGS,
    _SKIP_TAGS,
    clean_text,
    count_words,
    get_all_text,
    get_scriptrefs,
    preprocess_thml,
)

log = logging.getLogger("ccel_creeds_of_christendom")

SCHEMA_VERSION = "2.1.0"
SCRIPT_VERSION = "v2.0.0"
PROVENANCE_DATE = "2026-09-17"
WRITER_IDENTITY = "ccel_creeds_of_christendom_parser"
OUTPUT_DIR = REPO_ROOT / "data" / "structured-text"

VOLUMES = {
    1: {
        "title": "The Creeds of Christendom, Vol. I: The History of Creeds",
        "work_kind": "church-history",
        "description": (
            "surveys the creeds and confessions of all major Christian traditions -- "
            "Greek, Roman, Lutheran, Reformed, and modern evangelical"
        ),
    },
    2: {
        "title": "The Creeds of Christendom, Vol. II: The Greek and Latin Creeds",
        "work_kind": "theological-work",
        "description": (
            "collects Scripture confessions, ancient rules of faith, the ecumenical "
            "creeds, and Greek, Russian, and Roman doctrinal standards with translations"
        ),
    },
    3: {
        "title": "The Creeds of Christendom, Vol. III: The Evangelical Protestant Creeds",
        "work_kind": "theological-work",
        "description": (
            "collects Lutheran, Reformed, Anglican, Congregational, Baptist, Quaker, "
            "Moravian, Methodist, and other Protestant confessions"
        ),
    },
}

# Backward-compatible name used by the existing Volume I schema test.
WORK_KIND = VOLUMES[1]["work_kind"]

WORK_META = {
    "author": "Philip Schaff",
    "author_birth_year": 1819,
    "author_death_year": 1893,
    "contributors": [
        {"name": "David S. Schaff", "role": "reviser"},
        {"name": "Christian Classics Ethereal Library", "role": "transcriber"},
        {"name": "Charles Bowen", "role": "editor"},
    ],
    "original_publication_year": 1877,
    "language": "en",
    "original_language": "en",
    "tradition": ["ecumenical"],
    "era": "modern",
    "audience": "scholarly",
    "license": "public-domain",
    "completeness": "full",
}

_ROMAN_VOLUME = {1: "I", 2: "II", 3: "III"}
_SCOPE_NOTES = {
    1: (
        "Eight top-level history chapters are ingested. Title Page, all Prefatory "
        "matter, the table of contents, and indexes are excluded."
    ),
    2: (
        "Six top-level content divisions are ingested. Title Page, Subject Index, "
        "and generated Indexes are excluded."
    ),
    3: (
        "Four top-level parts are ingested. The malformed CCEL 'Original Table of "
        "Contents' wrapper contains the Lutheran texts of Part First, so the wrapper "
        "is relabeled as Part First rather than indexed as a table of contents; the "
        "Title Page, Index to Vol. III, and generated Indexes are excluded."
    ),
}


def _source_edition(volume: int) -> str:
    return (
        "Philip Schaff, The Creeds of Christendom, with a History and Critical "
        "Notes, sixth edition, revised and enlarged by David S. Schaff (1931), "
        f"Vol. {_ROMAN_VOLUME[volume]}; original three-volume edition published "
        "in 1877; Christian Classics Ethereal Library (CCEL) ThML transcription"
    )

# div1 content chapters are titled "Chapter N. ..."; front/back matter (Title
# Page, Prefatory, Index to Volume I, Indexes) is everything else.
_CHAPTER_DIV1_RE = re.compile(r"^\s*Chapter\s", re.IGNORECASE)
_CHAPTER_PREFIX_RE = re.compile(r"^\s*(Chapter\s+\w+)\.?\s*(.*)$", re.IGNORECASE)

_SECTION_TYPE_BY_DEPTH = {0: "chapter", 1: "section", 2: "subsection"}


def _label_title(div: ET.Element, depth: int) -> tuple[str | None, str | None]:
    """Derive (label, title) for a div at the given nesting depth."""
    n = div.get("n", "")
    title_attr = clean_text(div.get("title", ""))

    if depth == 0:
        m = _CHAPTER_PREFIX_RE.match(title_attr)
        if m:
            rest = m.group(2).strip().rstrip(".").strip()
            return m.group(1), (rest or None)
        label = f"Chapter {n}" if n else None
        return label, (title_attr.rstrip(".").strip() or None)

    label = f"§ {n}" if n else None
    return label, (title_attr or None)


def parse_div(div: ET.Element, depth: int) -> dict | None:
    """Recursively parse a div element into a structured_text section dict.

    Own paragraphs (<p>/<q>/<argument>/lists) become content_blocks; nested divs
    become children one level deeper. Returns None when the div has neither.
    """
    section_type = _SECTION_TYPE_BY_DEPTH.get(depth, "subsection")
    label, title = _label_title(div, depth)

    content_blocks: list[str] = []
    children: list[dict] = []
    for child in div:
        if _DIV_TAG_RE.match(child.tag):
            sub = parse_div(child, depth + 1)
            if sub is not None:
                children.append(sub)
            continue
        if child.tag in _SKIP_TAGS or child.tag in _HEADING_TAGS:
            continue
        if child.tag in ("p", "argument", "q"):
            text = clean_text(get_all_text(child))
            if text:
                content_blocks.append(text)
        elif child.tag in ("ul", "ol"):
            items = [
                clean_text(get_all_text(li))
                for li in child.findall("li")
                if clean_text(get_all_text(li))
            ]
            if items:
                content_blocks.append("; ".join(items))

    if not content_blocks and not children:
        return None

    own_wc = count_words(content_blocks)
    total_wc = own_wc + sum(c["word_count"] for c in children)
    return {
        "section_type": section_type,
        "label": label,
        "title": title,
        "content_blocks": content_blocks,
        "scripture_references": get_scriptrefs(div),
        "word_count": total_wc,
        "children": children,
    }


def _paths(volume: int) -> tuple[Path, Path, str, str]:
    if volume not in VOLUMES:
        raise ValueError(f"unsupported volume: {volume}")
    work_id = f"creeds-of-christendom-vol-{volume}"
    raw_file = REPO_ROOT / "raw" / "ccel" / "schaff" / f"creeds{volume}.xml"
    output_file = OUTPUT_DIR / f"{work_id}.json"
    source_url = f"https://www.ccel.org/ccel/schaff/creeds{volume}.xml"
    return raw_file, output_file, source_url, work_id


def _is_content_div(volume: int, title: str) -> bool:
    if volume == 1:
        return bool(_CHAPTER_DIV1_RE.match(title))
    if volume == 2:
        return title not in {"Title Page", "Subject Index", "Indexes"}
    return title not in {"Title Page", "Index to Vol. III", "Indexes"}


def parse_creeds_volume(volume: int = 1, dry_run: bool = False) -> dict:
    """Parse one CCEL volume into a structured_text data dictionary."""
    raw_file, _, _, work_id = _paths(volume)
    if not raw_file.exists():
        raise FileNotFoundError(f"missing source: {raw_file}")

    raw_bytes = raw_file.read_bytes()
    source_hash = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    root = ET.fromstring(preprocess_thml(raw_bytes))

    body = root.find("ThML.body")
    if body is None:
        raise RuntimeError("No <ThML.body> in creeds1.xml")

    sections: list[dict] = []
    for div1 in body:
        if not _DIV_TAG_RE.match(div1.tag):
            continue
        title_attr = clean_text(div1.get("title", ""))
        if not _is_content_div(volume, title_attr):
            continue  # skip Title Page / Prefatory / Index div1s
        ch = parse_div(div1, depth=0)
        if ch is not None:
            if volume == 3 and title_attr == "Original Table of Contents":
                ch["title"] = "Part First. The Creeds of the Evangelical Lutheran Churches"
            sections.append(ch)
        if dry_run and len(sections) >= 2:
            break

    if not sections:
        raise RuntimeError("No content chapters found in creeds1.xml")

    return {
        "work_id": work_id,
        "work_kind": VOLUMES[volume]["work_kind"],
        "sections": sections,
        "_source_hash": source_hash,
    }


def build_meta(volume: int, source_hash: str) -> dict:
    _, _, source_url, work_id = _paths(volume)
    volume_meta = VOLUMES[volume]

    return {
        "id": work_id,
        "title": volume_meta["title"],
        "author": WORK_META["author"],
        "author_birth_year": WORK_META["author_birth_year"],
        "author_death_year": WORK_META["author_death_year"],
        "contributors": normalize_contributors(WORK_META["contributors"]),
        "original_publication_year": WORK_META["original_publication_year"],
        "edition": "Sixth edition, revised and enlarged (1931)",
        "language": WORK_META["language"],
        "original_language": WORK_META["original_language"],
        "tradition": WORK_META["tradition"],
        "tradition_notes": (
            "Schaff was a Swiss-American Reformed theologian and church historian. "
            f"This volume {volume_meta['description']}."
        ),
        "era": WORK_META["era"],
        "audience": WORK_META["audience"],
        "license": WORK_META["license"],
        "schema_type": "structured_text",
        "schema_version": SCHEMA_VERSION,
        "completeness": WORK_META["completeness"],
        "provenance": {
            "source_url": source_url,
            "source_format": "ThML XML",
            "source_edition": _source_edition(volume),
            "download_date": PROVENANCE_DATE,
            "source_hash": source_hash,
            "processing_method": "automated",
            "processing_script_version": (
                f"build/parsers/ccel_creeds_of_christendom.py@{SCRIPT_VERSION}"
            ),
            "processing_date": PROVENANCE_DATE,
            "notes": (
                "ThML HTML entities replaced with Unicode equivalents; DOCTYPE "
                "stripped before parsing. Footnotes (<note>) and page breaks "
                "(<pb>) excluded from content. "
                f"{_SCOPE_NOTES[volume]} Divisions are recursed through nested divs. "
                "The potentially non-public-domain 1931 Preface to the Sixth Edition "
                "is excluded from searchable content. The retained edition text carries "
                "copyright notices for 1877, 1905, and 1919, publications now in the "
                "public domain in the United States; downstream users outside the United "
                "States must check local law."
            ),
        },
    }


def _report_quality(data: dict) -> None:
    chapters = data["sections"]

    def _walk(secs):
        for s in secs:
            yield s
            yield from _walk(s.get("children", []))

    all_secs = list(_walk(chapters))
    total_words = sum(ch["word_count"] for ch in chapters)
    wcs = [s["word_count"] for s in all_secs if s["word_count"] > 0]
    log.info("  %d chapters, %d total sections, %d words", len(chapters), len(all_secs), total_words)
    if wcs:
        log.info("  section wc min/med/max: %d/%d/%d", min(wcs), sorted(wcs)[len(wcs) // 2], max(wcs))
    empty = sum(1 for s in all_secs if not s["content_blocks"])
    if empty:
        log.info("  %d sections with no own content_blocks (container-only)", empty)


def write_source_config(volume: int, source_hash: str, *, repo_root: Path = REPO_ROOT) -> Path:
    _, _, source_url, work_id = _paths(volume)
    volume_meta = VOLUMES[volume]
    config_dir = repo_root / "sources" / "structured-text" / work_id
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    config = {
        "resource_id": work_id,
        "title": volume_meta["title"],
        "author": WORK_META["author"],
        "author_birth_year": WORK_META["author_birth_year"],
        "author_death_year": WORK_META["author_death_year"],
        "contributors": normalize_contributors(WORK_META["contributors"]),
        "original_publication_year": WORK_META["original_publication_year"],
        "edition": "Sixth edition, revised and enlarged (1931)",
        "language": WORK_META["language"],
        "original_language": WORK_META["original_language"],
        "tradition": WORK_META["tradition"],
        "era": WORK_META["era"],
        "audience": WORK_META["audience"],
        "license": WORK_META["license"],
        "schema_type": "structured_text",
        "work_kind": volume_meta["work_kind"],
        "source_url": source_url,
        "source_format": "ThML XML",
        "source_edition": _source_edition(volume),
        "download_date": PROVENANCE_DATE,
        "source_hash": source_hash,
        "processing_method": "automated",
        "processing_script_version": f"build/parsers/ccel_creeds_of_christendom.py@{SCRIPT_VERSION}",
        "processing_date": PROVENANCE_DATE,
    }
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return config_path


def write_output(volume: int, data: dict, *, repo_root: Path = REPO_ROOT) -> None:
    work_id = f"creeds-of-christendom-vol-{volume}"
    output_file = repo_root / "data" / "structured-text" / f"{work_id}.json"
    source_hash = data.pop("_source_hash")
    meta = build_meta(volume, source_hash)
    envelope = {"meta": meta, "data": data}
    previous = load_json(output_file)
    with writer_manifest.run(
        writer_identity=WRITER_IDENTITY,
        writer_version=f"build/parsers/ccel_creeds_of_christendom.py@{SCRIPT_VERSION}",
        data_paths=[output_file],
        repo_root=repo_root,
        manifests_dir=repo_root / "review" / "writer-manifests",
    ) as manifest_run:
        write_json(output_file, envelope)
        entries_changed, fields_changed = envelope_delta_counts(previous, envelope)
        manifest_run.record_delta(output_file, entries_changed=entries_changed, fields_changed=fields_changed)
        # PIPE-19: verify written tree matches in-memory.
        reread = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(reread["data"]["sections"]) == len(data["sections"]), "write verification failed"
        log.info("  wrote %s (%d chapters)", output_file, len(data["sections"]))
        write_source_config(volume, source_hash, repo_root=repo_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--volume", choices=("1", "2", "3", "all"), default="1", help="Volume to parse."
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse 2 chapters, do not write.")
    parser.add_argument("--parse", action="store_true", help="Parse and write the output file.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    volumes = (1, 2, 3) if args.volume == "all" else (int(args.volume),)
    for volume in volumes:
        data = parse_creeds_volume(volume, dry_run=args.dry_run)
        _report_quality(data)

        if args.dry_run or not args.parse:
            print(
                f"Parsed volume {volume}: {len(data['sections'])} top-level sections "
                "(dry-run; no file written)."
            )
            continue

        section_count = len(data["sections"])
        write_output(volume, data)
        print(f"Done: volume {volume}, {section_count} top-level sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
