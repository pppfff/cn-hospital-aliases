"""Load China healthcare reference identities from an official ROR data dump."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def read_china_healthcare(zip_path: Path, metadata_path: Path) -> tuple[list[dict], dict]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = metadata["files"][0]["checksum"]
    actual = "md5:" + hashlib.md5(zip_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"ROR download checksum mismatch: {actual} != {expected}")
    with ZipFile(zip_path) as archive:
        files = [name for name in archive.namelist() if name.endswith(".json") and ("schema_v2" in name or name.startswith("v2."))]
        if len(files) != 1:
            raise ValueError(f"Expected one ROR schema_v2 JSON file, found {files}")
        with archive.open(files[0]) as handle:
            records = json.load(handle)
    selected = [
        row for row in records
        if "healthcare" in row["types"]
        and any(location["geonames_details"]["country_code"] == "CN" for location in row["locations"])
    ]
    manifest = {
        "source": "Research Organization Registry", "license": "CC0-1.0",
        "source_url": metadata["doi_url"], "version": metadata["metadata"]["version"],
        "publication_date": metadata["metadata"]["publication_date"],
        "checksum": actual, "china_healthcare_records": len(selected),
        "all_dump_records": len(records), "schema_file": files[0],
        "identity_evidence": "reference_curated; not an official Chinese legal-name certification",
    }
    return sorted(selected, key=lambda row: row["id"]), manifest
