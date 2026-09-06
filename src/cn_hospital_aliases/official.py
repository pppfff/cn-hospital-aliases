"""Filing-anchored site identities with approved aliases separated from leads."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from .master import PROVINCE_EN, apply_reviews, apply_verified_seed, reference_entities
from .normalizer import normalize_name
from .sources.clinicaltrials_gov import _gzip_text_writer

APPROVED_EVIDENCE = {"official_filing", "official_source_reviewed", "seed_source_reviewed"}
OFFICIAL_IDENTIFIERS = {"cfdi_company_id", "cfdi_drug_filing", "cn_uscc", "legacy_project_id"}


def official_records(filings, ror, *, reviews, decisions, accessed_at, include_seed=True):
    """One identity per filing ID; never create identities from reported names."""
    if not filings or len({row["companyId"] for row in filings}) != len(filings):
        raise ValueError("Official filings must be nonempty and have unique company IDs")
    if any(not row["companyId"] or not row["compName"] or not row["recordNo"] for row in filings):
        raise ValueError("Official identity, literal name and filing number are required")
    entities = reference_entities(filings, ror, accessed_at=accessed_at, decisions=decisions)
    apply_reviews(entities, reviews)
    if include_seed:
        apply_verified_seed(entities)
    records, assertions, candidates = [], [], []
    priority = {"official_source_reviewed": 0, "official_filing": 1, "seed_source_reviewed": 2}
    for filing in sorted(filings, key=lambda item: item["companyId"]):
        key = "cnha-cfdi-" + filing["companyId"].lower()
        entity = entities[key]
        # Preserve the entire registered name, including parentheses and campus
        # qualifiers, rather than selecting the first split display name.
        canonical = filing["compName"]
        approved = {normalize_name(canonical): {"name": canonical, "kind": "canonical", "source_url": filing["source_url"], "accessed_at": filing["accessed_at"], "evidence_status": "official_filing"}}
        for name in sorted(entity["names"], key=lambda item: priority.get(item["evidence_status"], 3)):
            if name["evidence_status"] in APPROVED_EVIDENCE:
                approved.setdefault(normalize_name(name["name"]), name)
        aliases = []
        accepted_normalized = {normalize_name(canonical)}
        for normalized, name in approved.items():
            # A filing may contain a hospital plus a school, institute, campus,
            # or internet-hospital label in one display field. Keep the literal
            # field as the official identity; split components require a
            # separate official-source review before becoming aliases.
            if name["evidence_status"] == "official_filing" and name["kind"] != "canonical":
                continue
            accepted_normalized.add(normalized)
            kind = "canonical" if normalized == normalize_name(canonical) else ("official_variant" if name["kind"] == "canonical" else name["kind"])
            assertions.append({"hospital_id": key, "official_name": canonical, "filing_number": filing["recordNo"], "alias": name["name"], "normalized_alias": normalized, "kind": kind, "evidence_status": name["evidence_status"], "source_url": name["source_url"], "accessed_at": name["accessed_at"], "valid_from": name.get("valid_from"), "valid_to": name.get("valid_to")})
            if kind != "canonical":
                aliases.append({"name": name["name"], "kind": kind, "source_url": name["source_url"], "accessed_at": name["accessed_at"], "note": name["evidence_status"], "valid_from": name.get("valid_from"), "valid_to": name.get("valid_to")})
        for name in entity["names"]:
            if normalize_name(name["name"]) not in accepted_normalized:
                candidates.append({"hospital_id": key, "official_name": canonical, "candidate_alias": name["name"], "source_url": name["source_url"], "status": "review_required", "reason": "Reference-only name; not approved for resolution"})
        english = next((alias["name"] for alias in aliases if alias["kind"] == "english_name"), "")
        province_aliases = [PROVINCE_EN[entity["province_code"]]] if entity["province_code"] in PROVINCE_EN else []
        if entity["province_code"] in {"BJ", "TJ", "SH", "CQ"}:
            province_aliases.append(PROVINCE_EN[entity["province_code"]] + " Municipality")
        records.append({"hospital_id": key, "canonical_name": canonical, "official_name_zh": canonical,
                        "province": entity["province"] or "Unknown", "city": entity["city"] or "Unknown",
                        "city_aliases": sorted(entity["city_keys"] - {""}),
                        "province_aliases": province_aliases,
                        "source_url": filing["source_url"], "accessed_at": filing["accessed_at"],
                        "source_registry": "NMPA/CFDI drug-trial institution filings", "verification_status": "official_filing",
                        "filing_status": entity["filing_status"], "filing_number": filing["recordNo"],
                        "identifiers": [item for item in entity["identifiers"] if item["scheme"] in OFFICIAL_IDENTIFIERS],
                        "aliases": aliases, "english_name": english,
                        "official_review_completed": entity["official_review_completed"]})
    return records, assertions, candidates


def write_official(records, assertions, candidates, *, directory: Path, package_output: Path):
    directory.mkdir(parents=True, exist_ok=True)
    package_output.parent.mkdir(parents=True, exist_ok=True)
    with _gzip_text_writer(package_output) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    institutions = [{field: row[field] for field in ("hospital_id", "canonical_name", "filing_number", "filing_status", "province", "city", "english_name", "source_url", "accessed_at")} for row in records]
    for filename, rows, fields in (
        ("official_institutions.csv", institutions, list(institutions[0])),
        ("approved_aliases.csv", assertions, list(assertions[0])),
        ("alias_review_queue.csv", candidates, ["hospital_id", "official_name", "candidate_alias", "source_url", "status", "reason"]),
    ):
        with (directory / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    by_name = defaultdict(set)
    for row in assertions:
        by_name[row["normalized_alias"]].add(row["hospital_id"])
    summary = {"purpose": "Map site aliases to official filing identities, not rank hospitals by trial volume",
               "official_institutions": len(records), "approved_name_assertions": len(assertions),
               "noncanonical_aliases": sum(len(row["aliases"]) for row in records),
               "institutions_with_aliases": sum(bool(row["aliases"]) for row in records),
               "reference_only_candidates_not_approved": len(candidates),
               "ambiguous_normalized_names": sum(len(keys) > 1 for keys in by_name.values()),
               "filing_status_counts": dict(Counter(row["filing_status"] for row in records)),
               "nmpa_trial_detail_required_for_build": False,
               "limitations": "Snapshot-based name normalization; no assertion of current trial eligibility, all historical aliases or legal-entity continuity across separate filings"}
    (directory / "quality_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
