from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED_DATE = "2026-09-17"
EXPANSION_WRITERS = {
    "build/parsers/ccel_arminius_works.py@v1.0.0",
    "build/parsers/ccel_creeds_of_christendom.py@v2.0.0",
    "build/parsers/ccel_dionysius_works.py@v1.0.0",
    "build/parsers/project_wittenberg_boc.py@v1.0.1",
    "build/parsers/public_domain_expansion.py@v1.0.0",
    "build/parsers/schaff_ecumenical_creeds.py@v1.0.0",
}


def _expansion_records() -> list[tuple[Path, dict]]:
    records: list[tuple[Path, dict]] = []
    for path in sorted((REPO_ROOT / "data").glob("**/*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        provenance = payload.get("meta", {}).get("provenance", {})
        if provenance.get("processing_script_version") in EXPANSION_WRITERS:
            records.append((path, payload))
    return records


def test_all_expansion_outputs_and_configs_use_pinned_provenance_dates():
    records = _expansion_records()

    assert len(records) == 22  # 20 net-new works plus two corrected existing records.
    for _path, payload in records:
        resource_id = payload["meta"]["id"]
        provenance = payload["meta"]["provenance"]
        assert provenance["download_date"] == PINNED_DATE
        assert provenance["processing_date"] == PINNED_DATE

        configs = list((REPO_ROOT / "sources").glob(f"**/{resource_id}/config.json"))
        assert len(configs) == 1, resource_id
        config = json.loads(configs[0].read_text(encoding="utf-8"))
        assert config["download_date"] == PINNED_DATE
        assert config["processing_date"] == PINNED_DATE
        assert config["source_hash"] == provenance["source_hash"]
        assert config["processing_script_version"] == provenance["processing_script_version"]
