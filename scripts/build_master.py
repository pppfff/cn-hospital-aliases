"""Build an institution master, evidence tables and the top-1000 review queue."""
import argparse
import csv
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path

from cn_hospital_aliases.master import build_master, expand_website_reviews
from cn_hospital_aliases.sources.cfdi import read_institutions
from cn_hospital_aliases.sources.nmpa import read_participation_csv
from cn_hospital_aliases.sources.ror import read_china_healthcare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cfdi-dir", type=Path, default=Path("data/raw/cfdi/2026-09-05-batch100"))
    parser.add_argument("--ror-zip", type=Path)
    parser.add_argument("--ror-metadata", type=Path)
    parser.add_argument("--nmpa-csv", type=Path)
    parser.add_argument("--rank-by", choices=("ctg", "nmpa"), default="ctg")
    parser.add_argument("--reviews", type=Path, default=Path("data/curated/official_reviews.json"))
    parser.add_argument("--decisions", type=Path, default=Path("data/curated/reference_decisions.json"))
    parser.add_argument("--website-reviews", type=Path, default=Path("data/curated/website_identity_reviews.json"))
    parser.add_argument("--accessed-at", default=date.today().isoformat())
    args = parser.parse_args()
    filings = read_institutions(args.cfdi_dir)
    raw_dir = Path("data/raw/ror")
    raw_dir.mkdir(parents=True, exist_ok=True)
    subset_path = raw_dir / "china_healthcare.json"
    if args.ror_zip or args.ror_metadata:
        if not (args.ror_zip and args.ror_metadata):
            parser.error("--ror-zip and --ror-metadata must be supplied together")
        ror, manifest = read_china_healthcare(args.ror_zip, args.ror_metadata)
        subset_path.write_text(json.dumps(ror, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["subset_sha256"] = hashlib.sha256(subset_path.read_bytes()).hexdigest()
        (raw_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
        if hashlib.sha256(subset_path.read_bytes()).hexdigest() != manifest["subset_sha256"]:
            raise ValueError("Cached ROR subset checksum mismatch")
        ror = json.loads(subset_path.read_text(encoding="utf-8"))
    with gzip.open("data/processed/facility_mentions.csv.gz", "rt", encoding="utf-8") as handle:
        mentions = list(csv.DictReader(handle))
    if args.nmpa_csv:
        nmpa_rows = read_participation_csv(args.nmpa_csv)
        if not nmpa_rows:
            parser.error("The NMPA export contains no participation rows")
        mentions.extend(nmpa_rows)
    reviews = json.loads(args.reviews.read_text(encoding="utf-8")) if args.reviews.exists() else []
    decisions = json.loads(args.decisions.read_text(encoding="utf-8")) if args.decisions.exists() else {}
    if args.website_reviews.exists():
        website_links, website_reviews = expand_website_reviews(json.loads(args.website_reviews.read_text(encoding="utf-8")))
        decisions.setdefault("ror_to_cfdi", []).extend(website_links)
        reviews = website_reviews + reviews
    summary = build_master(filings, ror, mentions, output_dir=Path("data/master"), package_output=Path("src/cn_hospital_aliases/data/hospital_master.jsonl.gz"), reviews=reviews, decisions=decisions, nmpa_records_available=bool(args.nmpa_csv), accessed_at=args.accessed_at, rank_by=args.rank_by)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
