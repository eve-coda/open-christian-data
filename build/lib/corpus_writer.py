"""Small shared helpers for whole-envelope corpus writers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object at {path}")
    return payload


def write_json(path: Path, payload: Mapping) -> None:
    """Write deterministic UTF-8 JSON through an atomic sibling replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def envelope_delta_counts(before: Mapping | None, after: Mapping) -> tuple[int, int]:
    """Count one changed envelope and its changed top-level fields."""
    if before == after:
        return 0, 0
    previous = before or {}
    changed_fields = sum(
        previous.get(field) != after.get(field)
        for field in set(previous) | set(after)
    )
    return 1, changed_fields


def manifest_delta_counts(before: Mapping | None, after: Mapping) -> tuple[int, int]:
    """Count changed collection-manifest document entries by stable id."""
    previous_entries = {
        entry["id"]: entry
        for entry in (before or {}).get("documents", [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    current_entries = {
        entry["id"]: entry
        for entry in after.get("documents", [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    entries_changed = 0
    fields_changed = 0
    for entry_id in set(previous_entries) | set(current_entries):
        previous = previous_entries.get(entry_id) or {}
        current = current_entries.get(entry_id) or {}
        if previous == current:
            continue
        entries_changed += 1
        fields_changed += sum(
            previous.get(field) != current.get(field)
            for field in set(previous) | set(current)
        )
    return entries_changed, fields_changed
