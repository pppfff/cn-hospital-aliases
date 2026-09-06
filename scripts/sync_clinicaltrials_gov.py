#!/usr/bin/env python3
"""Refresh the China interventional trial-site snapshot."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from cn_hospital_aliases import HospitalRegistry
from cn_hospital_aliases.sources.clinicaltrials_gov import (
    aggregate_sites,
    extract_mentions,
    fetch_all_study_pages,
    write_snapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=PROJECT_ROOT / "data/raw/clinicaltrials_gov",
    )
    parser.add_argument(
        "--processed-dir", type=Path, default=PROJECT_ROOT / "data/processed"
    )
    parser.add_argument(
        "--review-dir", type=Path, default=PROJECT_ROOT / "data/review"
    )
    parser.add_argument(
        "--package-output",
        type=Path,
        default=PROJECT_ROOT
        / "src/cn_hospital_aliases/data/clinical_trial_hospitals.jsonl.gz",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-pages", type=int)
    args = parser.parse_args()

    manifest = fetch_all_study_pages(
        args.raw_dir, refresh=args.refresh, max_pages=args.max_pages
    )
    if not manifest["complete"]:
        print("snapshot is incomplete; download can be resumed, transformation skipped")
        return 1

    pages = sorted(args.raw_dir.glob("page-*.json"))
    mentions = extract_mentions(pages)
    sites = aggregate_sites(mentions)
    stats = write_snapshot(
        mentions,
        sites,
        processed_dir=args.processed_dir,
        review_dir=args.review_dir,
        package_output=args.package_output,
        verified_registry=HospitalRegistry.load_default(),
        accessed_at=date.today().isoformat(),
        total_study_count=manifest.get("total_study_count"),
        source_data_timestamp=manifest.get("api_version", {}).get("dataTimestamp"),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
