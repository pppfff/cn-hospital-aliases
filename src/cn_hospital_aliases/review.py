"""Reconcile each frozen review row with evidence; never approve new names."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from .normalizer import normalize_name
from .registry import HospitalRegistry


def chinese_name_reviews(document: dict, filings: list[dict]) -> list[dict]:
    """Expand explicit human-reviewed decisions; never approve by string shape."""
    by_id = {"cnha-cfdi-" + row["companyId"].lower(): row for row in filings}
    reviews = []
    seen = set()
    for row in document["decisions"]:
        if row["decision"] == "retain_unapproved":
            continue
        if row["decision"] != "approve_parallel_hospital_name":
            raise ValueError("Unknown Chinese review decision")
        filing = by_id[row["hospital_id"]]
        name = row["candidate_alias"]
        key = (row["hospital_id"], normalize_name(name))
        if (not name or row["official_name"] != filing["compName"]
                or name not in filing["compName"]
                or row["source_url"] != filing["source_url"]
                or not row.get("accessed_at") or key in seen):
            raise ValueError("Chinese review does not match its pinned filing evidence")
        seen.add(key)
        reviews.append({"hospital_id": row["hospital_id"], "official_review_completed": False,
                        "names": [{"value": name, "kind": "parallel_name",
                                   "source_url": row["source_url"], "accessed_at": row["accessed_at"]}]})
    return reviews


def institution_confirmation_register(directory: Path, registry: HospitalRegistry,
                                      filings: list[dict]) -> dict:
    """Confirm snapshot identities independently of optional English fields."""
    by_id = {"cnha-cfdi-" + row["companyId"].lower(): row for row in filings}
    if len(by_id) != len(filings) or {h.hospital_id for h in registry.hospitals} != set(by_id):
        raise ValueError("Filing identity inventory differs from registry")
    pending = defaultdict(list)
    with (directory / "alias_review_queue.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            pending[row["hospital_id"]].append(row)
    rows = []
    for hospital in registry.hospitals:
        filing = by_id[hospital.hospital_id]
        if (hospital.canonical_name != filing["compName"]
                or hospital.filing_number != filing["recordNo"]
                or hospital.source_url != filing["source_url"]):
            raise ValueError("Official Chinese identity disagrees with filing")
        rows.append({
            "hospital_id": hospital.hospital_id, "official_name_zh": hospital.canonical_name,
            "filing_number": hospital.filing_number, "filing_status": hospital.filing_status,
            "identity_confirmation_status": "confirmed_against_filing_snapshot",
            "english_name": hospital.english_name or "",
            "english_review_status": "source_reviewed" if hospital.english_name else "deferred_not_required_for_identity",
            "approved_alias_count": len(hospital.aliases),
            "pending_aliases_json": json.dumps(pending[hospital.hospital_id], ensure_ascii=False),
            "all_identity_fields_reviewed": hospital.official_review_completed,
            "source_url": filing["source_url"], "accessed_at": filing["accessed_at"],
            "scope": "Snapshot identity only; not all aliases, trial participation or current eligibility",
        })
    with (directory / "institution_confirmation_register.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["hospital_id"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {"filing_identities_confirmed": len(rows),
               "english_status_counts": dict(Counter(row["english_review_status"] for row in rows)),
               "english_required_for_identity": False,
               "all_research_center_aliases_confirmed": False,
               "scope": "Pinned CFDI filing snapshot; separate from trial-site alias confirmation"}
    (directory / "institution_confirmation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def verification_register(directory: Path, registry: HospitalRegistry) -> dict:
    baseline = directory / "trial_site_review_baseline.csv"
    with baseline.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    evidence, leads = defaultdict(list), defaultdict(list)
    for filename, column, index in (
        ("approved_aliases.csv", "alias", evidence),
        ("alias_review_queue.csv", "candidate_alias", leads),
    ):
        with (directory / filename).open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                index[normalize_name(row[column])].append(row)
    register = []
    for rank, row in enumerate(rows, 1):
        name = row["canonical_reported_name"]
        key = normalize_name(name)
        matches = registry.resolve(name)
        filtered = registry.resolve(name, province=row["province_reported"] or None, city=row["city_reported"] or None)
        if len(matches) == 1:
            name_status = "verified_name_relation"
        elif matches:
            name_status = "ambiguous_name_relation"
        elif leads[key]:
            name_status = "unverified_reference_only"
        else:
            name_status = "unverified_no_approved_evidence"
        chosen = filtered[0] if len(filtered) == 1 else None
        if chosen:
            location_status = "passes_available_location_filters"
            next_action = "Retain source-backed name mapping; assess actual study/campus scope separately when needed"
        elif matches:
            location_status = "requires_location_review"
            next_action = "Verify reported province, city and campus against the study record before assigning an institution ID"
        else:
            location_status = "not_evaluated_without_approved_identity"
            next_action = "Obtain hospital or regulator evidence connecting the reported name to a filing; reference labels alone are insufficient"
        register.append({
            "baseline_rank": rank,
            "canonical_reported_name": name,
            "province_reported": row["province_reported"],
            "city_reported": row["city_reported"],
            "trial_count_within_name_group": row["trial_count"],
            "trial_example_url": row["source_url"],
            "name_verification_status": name_status,
            "location_verification_status": location_status,
            "official_hospital_id": chosen.hospital.hospital_id if chosen else "",
            "official_name": chosen.hospital.canonical_name if chosen else "",
            "filing_number": chosen.hospital.filing_number if chosen else "",
            "approved_name_evidence_json": json.dumps(evidence[key], ensure_ascii=False),
            "unapproved_reference_leads_json": json.dumps(leads[key], ensure_ascii=False),
            "next_action": next_action,
            "check_method": "deterministic reconciliation of source-reviewed assertions; not a new manual source review",
        })
    output = directory / "trial_site_verification_register.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = list(register[0]) if register else ["baseline_rank"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(register)
    statuses = Counter(row["name_verification_status"] for row in register)
    summary = {
        "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
        "rows_checked_against_available_evidence": len(register),
        "name_verification_status_counts": dict(statuses),
        "location_verification_status_counts": dict(Counter(row["location_verification_status"] for row in register)),
        "all_name_relations_verified": bool(register) and statuses["verified_name_relation"] == len(register),
        "new_manual_source_reviews_performed_by_script": 0,
    }
    (directory / "trial_site_verification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
