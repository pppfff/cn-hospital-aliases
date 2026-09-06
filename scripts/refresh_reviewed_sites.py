"""Apply approved names to all cached site groups and retain review progress."""
import csv
import json
from pathlib import Path
import shutil

from audit_trial_site_coverage import audit
from cn_hospital_aliases import HospitalRegistry
from cn_hospital_aliases.review import verification_register


def main():
    directory = Path("data/official")
    baseline = directory / "trial_site_review_baseline.csv"
    if not baseline.exists():
        shutil.copyfile(directory / "trial_site_alias_review_queue.csv", baseline)
    registry = HospitalRegistry.load_default()
    reviewed = json.loads(Path("data/curated/trial_queue_reviews.json").read_text())
    from cn_hospital_aliases.normalizer import normalize_name
    decisions = {normalize_name(n["value"]): n for review in reviewed for n in review["names"]}
    with baseline.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        decision = decisions.get(normalize_name(row["canonical_reported_name"]))
        matches = registry.resolve(row["canonical_reported_name"])
        row["name_review_status"] = "official_name_verified_this_batch" if decision else "not_reviewed_this_batch"
        row["review_source_url"] = decision["source_url"] if decision else ""
        row["name_only_candidate_count"] = len(matches)
    with (directory / "trial_site_review_progress.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    hospital = audit(Path("data/processed/hospital_sites.csv.gz"), directory / "trial_site_coverage.csv", directory / "trial_site_alias_review_queue.csv", directory / "trial_site_coverage_summary.json")
    all_sites = audit(Path("data/processed/facility_sites.csv.gz"), directory / "all_site_coverage.csv", directory / "all_site_review_queue.csv", directory / "all_site_coverage_summary.json", queue_limit=1000000)
    print(json.dumps(verification_register(directory, registry), ensure_ascii=False, indent=2))
    print(json.dumps({"reviewed_institution_records": len(reviewed), "baseline_rows_with_new_name_evidence": sum(bool(row["review_source_url"]) for row in rows), "baseline_total": len(rows), "hospital_groups": hospital, "all_site_groups": all_sites}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
