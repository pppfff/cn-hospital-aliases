"""Audit reported trial-site names against the official filing registry.

This produces an evidence table for alias review. It never adds a reported
name to the approved alias table and never creates a new official identity.
"""
import argparse
import csv
import gzip
import json
from pathlib import Path

from cn_hospital_aliases import HospitalRegistry


def audit(input_path: Path, output_path: Path, queue_path: Path, summary_path: Path, *, queue_limit: int = 1000) -> dict:
    if queue_limit < 0:
        raise ValueError("queue_limit must be nonnegative")
    registry = HospitalRegistry.load_default()
    with gzip.open(input_path, "rt", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("Input site file is empty")
    required = {"canonical_reported_name", "province_reported", "city_reported"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Input site file is missing columns: {', '.join(sorted(missing))}")

    output_rows = []
    counts = {"matched": 0, "matched_location_conflict": 0, "ambiguous": 0, "unmatched": 0}
    trial_counts = {key: 0 for key in counts}
    for row in rows:
        matches = registry.resolve(
            row["canonical_reported_name"],
            province=row.get("province_reported") or None,
            city=row.get("city_reported") or None,
            fuzzy=False,
        )
        candidates = matches
        review_reason = ""
        if len(matches) == 1 and matches[0].match_type != "fuzzy":
            status = "matched"
            chosen = matches[0]
        elif not matches and (row.get("province_reported") or row.get("city_reported")):
            name_only = registry.resolve(row["canonical_reported_name"], fuzzy=False)
            candidates = name_only
            if len(name_only) == 1 and name_only[0].match_type != "fuzzy":
                status = "matched_location_conflict"
                chosen = None
                review_reason = "Approved name found, but reported location did not pass filters; review spelling, missing location aliases and actual conflicts"
            elif len(name_only) > 1:
                status = "ambiguous"
                chosen = None
                review_reason = "Multiple name candidates; reported location did not resolve identity"
            else:
                status = "unmatched"
                chosen = None
        elif len(matches) > 1:
            status = "ambiguous"
            chosen = None
        else:
            status = "unmatched"
            chosen = None
        count = int(row.get("trial_count") or 0)
        counts[status] += 1
        trial_counts[status] += count
        output_rows.append({
            **row,
            "resolution_status": status,
            "official_hospital_id": chosen.hospital.hospital_id if chosen else "",
            "official_name_zh": chosen.hospital.canonical_name if chosen else "",
            "filing_number": chosen.hospital.filing_number if chosen else "",
            "filing_status": chosen.hospital.filing_status if chosen else "",
            "matched_alias": chosen.matched_name if chosen else "",
            "match_type": chosen.match_type if chosen else "",
            "candidate_count": str(len(candidates)),
            "review_reason": review_reason,
            "candidates_json": json.dumps([{
                "hospital_id": match.hospital.hospital_id,
                "official_name": match.hospital.canonical_name,
                "filing_number": match.hospital.filing_number,
                "province": match.hospital.province,
                "city": match.hospital.city,
                "matched_alias": match.matched_name,
            } for match in candidates], ensure_ascii=False),
        })

    fields = list(output_rows[0])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    queue_rows = [row for row in output_rows if row["resolution_status"] != "matched"]
    queue_rows.sort(key=lambda row: (-int(row.get("trial_count") or 0), row["canonical_reported_name"]))
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_fields = ["canonical_reported_name", "province_reported", "city_reported", "trial_count", "active_trial_count", "name_variants", "resolution_status", "candidate_count", "first_trial_id", "source_url"]
    queue_fields += ["review_reason", "candidates_json"]
    with queue_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=queue_fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in queue_fields} for row in queue_rows[:queue_limit])

    summary = {
        "input": str(input_path),
        "official_registry": "NMPA/CFDI drug-trial institution filings",
        "input_site_rows": len(rows),
        "matched_site_rows": counts["matched"],
        "matched_location_conflict_rows": counts["matched_location_conflict"],
        "ambiguous_site_rows": counts["ambiguous"],
        "unmatched_site_rows": counts["unmatched"],
        "trial_count_by_status": trial_counts,
        "trial_count_definition": "Sum of within-group distinct trial counts; not globally distinct trials and not NMPA trial counts",
        "location_conflict_definition": "Name-only candidates exist but location filters rejected them; this may be a spelling or location-alias gap, not a proven geographic conflict",
        "review_queue_rows": min(len(queue_rows), queue_limit),
        "review_queue_limit": queue_limit,
        "fuzzy_matching_used": False,
        "approval_effect": "none; reported names remain review candidates",
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/hospital_sites.csv.gz"))
    parser.add_argument("--output", type=Path, default=Path("data/official/trial_site_coverage.csv"))
    parser.add_argument("--queue", type=Path, default=Path("data/official/trial_site_alias_review_queue.csv"))
    parser.add_argument("--summary", type=Path, default=Path("data/official/trial_site_coverage_summary.json"))
    parser.add_argument("--queue-limit", type=int, default=1000)
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output, args.queue, args.summary, queue_limit=args.queue_limit), ensure_ascii=False, indent=2))
