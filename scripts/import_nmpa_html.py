"""Import locally saved official NMPA trial detail pages listed in a manifest."""
import argparse
import csv
import json
from pathlib import Path

from cn_hospital_aliases.sources.nmpa import FIELDS, parse_detail_html


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON list of path, source_url, accessed_at objects")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not entries:
        parser.error("The manifest must contain at least one saved trial detail page")
    rows = []
    for entry in entries:
        path = args.manifest.parent / entry["path"]
        rows.extend(parse_detail_html(path.read_text(encoding="utf-8-sig"), source_url=entry["source_url"], accessed_at=entry["accessed_at"]))
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Imported {len(rows)} participation rows; coverage is limited to the supplied pages.")
